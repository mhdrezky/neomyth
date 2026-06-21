# openai/whisper-large-v3-turbo via faster-whisper (GPU recommended)

import io
import logging
import os
import tempfile
import wave

from fastapi import FastAPI, HTTPException, Request
from faster_whisper import WhisperModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

WHISPER_MODEL = os.getenv("WHISPER_MODEL", "large-v3-turbo")
WHISPER_DEVICE = os.getenv("WHISPER_DEVICE", "cuda")
WHISPER_COMPUTE_TYPE = os.getenv("WHISPER_COMPUTE_TYPE", "float16")
WHISPER_BEAM_SIZE = int(os.getenv("WHISPER_BEAM_SIZE", "5"))
WHISPER_LANGUAGE = os.getenv("WHISPER_LANGUAGE", "")

app = FastAPI(title="Whisper Large v3 STT Worker")
model: WhisperModel | None = None
active_device = WHISPER_DEVICE
active_compute_type = WHISPER_COMPUTE_TYPE


def _resolve_compute_type(device: str, compute_type: str) -> str:
    if device == "cpu":
        return "int8"
    return compute_type


def _load_whisper_model(device: str, compute_type: str) -> WhisperModel:
    compute_type = _resolve_compute_type(device, compute_type)
    logger.info(
        "Loading Whisper model=%s device=%s compute_type=%s beam=%s",
        WHISPER_MODEL,
        device,
        compute_type,
        WHISPER_BEAM_SIZE,
    )
    return WhisperModel(
        WHISPER_MODEL,
        device=device,
        compute_type=compute_type,
    )


def _warmup_transcribe(m: WhisperModel) -> None:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(b"\x00\x00" * 1600)
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp.write(buf.getvalue())
        path = tmp.name
    try:
        list(m.transcribe(path, beam_size=1))
    finally:
        os.unlink(path)


@app.on_event("startup")
def load_model() -> None:
    global model, active_device, active_compute_type
    try:
        model = _load_whisper_model(WHISPER_DEVICE, WHISPER_COMPUTE_TYPE)
        _warmup_transcribe(model)
        active_device = WHISPER_DEVICE
        active_compute_type = _resolve_compute_type(WHISPER_DEVICE, WHISPER_COMPUTE_TYPE)
        logger.info("Whisper large-v3-turbo ready on %s", active_device)
    except Exception as exc:
        if WHISPER_DEVICE == "cpu":
            raise
        logger.warning("CUDA init failed (%s), falling back to CPU (slower)", exc)
        model = _load_whisper_model("cpu", "int8")
        _warmup_transcribe(model)
        active_device = "cpu"
        active_compute_type = "int8"
        logger.info("Whisper large-v3-turbo ready on CPU fallback")


def _transcribe_kwargs() -> dict:
    kwargs: dict = {
        "beam_size": WHISPER_BEAM_SIZE,
        "vad_filter": True,
        "task": "transcribe",
        "condition_on_previous_text": False,
    }
    if WHISPER_LANGUAGE:
        kwargs["language"] = WHISPER_LANGUAGE
    return kwargs


def _run_transcribe(wav_path: str) -> str:
    global model, active_device, active_compute_type
    try:
        segments, _ = model.transcribe(wav_path, **_transcribe_kwargs())
        return " ".join(seg.text.strip() for seg in segments).strip()
    except RuntimeError as exc:
        err = str(exc)
        if active_device != "cpu" and ("CUDA" in err or "cublas" in err.lower()):
            logger.warning("GPU transcribe failed (%s), reloading on CPU", exc)
            model = _load_whisper_model("cpu", "int8")
            active_device = "cpu"
            active_compute_type = "int8"
            segments, _ = model.transcribe(wav_path, **_transcribe_kwargs())
            return " ".join(seg.text.strip() for seg in segments).strip()
        raise


@app.get("/health")
def health() -> dict[str, str | int]:
    return {
        "status": "ok",
        "model": WHISPER_MODEL,
        "hf_model": "openai/whisper-large-v3-turbo",
        "device": active_device,
        "compute_type": active_compute_type,
        "beam_size": WHISPER_BEAM_SIZE,
        "language": WHISPER_LANGUAGE or "auto",
    }


@app.post("/transcribe")
async def transcribe(request: Request) -> dict[str, str]:
    if model is None:
        raise HTTPException(status_code=503, detail="Model not loaded")

    audio_bytes = await request.body()
    pcm = _extract_pcm(audio_bytes)
    wav_bytes = _pcm_to_wav(pcm)

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp.write(wav_bytes)
        wav_path = tmp.name

    try:
        text = _run_transcribe(wav_path)
    except Exception as exc:
        logger.exception("Transcribe failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        os.unlink(wav_path)

    return {"text": text}


def _extract_pcm(data: bytes) -> bytes:
    if data[:4] == b"RIFF":
        with wave.open(io.BytesIO(data), "rb") as wf:
            return wf.readframes(wf.getnframes())
    return data


def _pcm_to_wav(pcm: bytes, sample_rate: int = 16000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm)
    return buf.getvalue()
