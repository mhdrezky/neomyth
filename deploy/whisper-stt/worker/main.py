"""Faster-Whisper STT inference worker."""

import io
import logging
import os
import tempfile
import wave

from fastapi import FastAPI, HTTPException, Request
from faster_whisper import WhisperModel

logger = logging.getLogger(__name__)

WHISPER_MODEL = os.getenv("WHISPER_MODEL", "Systran/faster-whisper-tiny")
WHISPER_DEVICE = os.getenv("WHISPER_DEVICE", "cpu")
WHISPER_COMPUTE_TYPE = os.getenv("WHISPER_COMPUTE_TYPE", "int8")
WHISPER_LANGUAGE = os.getenv("WHISPER_LANGUAGE", "")

app = FastAPI(title="Whisper STT Worker")
model: WhisperModel | None = None
active_device = WHISPER_DEVICE
active_compute_type = WHISPER_COMPUTE_TYPE


def _resolve_compute_type(device: str, compute_type: str) -> str:
    if device == "cpu" and compute_type in {"int8_float16", "float16", "float32"}:
        return "int8"
    return compute_type


def _load_whisper_model(device: str, compute_type: str) -> WhisperModel:
    compute_type = _resolve_compute_type(device, compute_type)
    logger.info(
        "Loading Whisper model=%s device=%s compute_type=%s",
        WHISPER_MODEL,
        device,
        compute_type,
    )
    return WhisperModel(
        WHISPER_MODEL,
        device=device,
        compute_type=compute_type,
    )


@app.on_event("startup")
def load_model() -> None:
    global model, active_device, active_compute_type
    try:
        model = _load_whisper_model(WHISPER_DEVICE, WHISPER_COMPUTE_TYPE)
        active_device = WHISPER_DEVICE
        active_compute_type = _resolve_compute_type(
            WHISPER_DEVICE, WHISPER_COMPUTE_TYPE
        )
    except Exception as exc:
        if WHISPER_DEVICE == "cpu":
            raise
        logger.warning("CUDA load failed (%s), falling back to CPU", exc)
        model = _load_whisper_model("cpu", "int8")
        active_device = "cpu"
        active_compute_type = "int8"


def _transcribe_kwargs() -> dict:
    kwargs: dict = {"beam_size": 1, "vad_filter": True, "task": "transcribe"}
    if WHISPER_LANGUAGE:
        kwargs["language"] = WHISPER_LANGUAGE
    return kwargs


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "model": WHISPER_MODEL,
        "device": active_device,
        "compute_type": active_compute_type,
        "language": WHISPER_LANGUAGE or "auto",
    }


@app.post("/transcribe")
async def transcribe(request: Request) -> dict[str, str]:
    global model, active_device, active_compute_type

    if model is None:
        raise HTTPException(status_code=503, detail="Model not loaded")

    audio_bytes = await request.body()
    pcm = _extract_pcm(audio_bytes)
    wav_bytes = _pcm_to_wav(pcm)

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp.write(wav_bytes)
        wav_path = tmp.name

    try:
        segments, _ = model.transcribe(wav_path, **_transcribe_kwargs())
        text = " ".join(seg.text.strip() for seg in segments).strip()
    except RuntimeError as exc:
        if "CUDA" in str(exc) and active_device != "cpu":
            logger.warning("CUDA transcribe failed (%s), reloading on CPU", exc)
            model = _load_whisper_model("cpu", "int8")
            active_device = "cpu"
            active_compute_type = "int8"
            segments, _ = model.transcribe(wav_path, **_transcribe_kwargs())
            text = " ".join(seg.text.strip() for seg in segments).strip()
        else:
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
