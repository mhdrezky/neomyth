"""Kokoro TTS inference worker."""

import logging
import os
import re
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)

KOKORO_VOICE = os.getenv("KOKORO_VOICE", "af_sarah")
KOKORO_LANG = os.getenv("KOKORO_LANG", "en-us")
KOKORO_MAX_CHARS = int(os.getenv("KOKORO_MAX_CHARS", "150"))
KOKORO_MODEL_PATH = os.getenv(
    "KOKORO_MODEL_PATH",
    "/app/models/kokoro-v1.0.onnx",
)
KOKORO_VOICES_PATH = os.getenv(
    "KOKORO_VOICES_PATH",
    "/app/models/voices-v1.0.bin",
)

MODEL_URL = (
    "https://github.com/thewh1teagle/kokoro-onnx/releases/download/"
    "model-files-v1.0/kokoro-v1.0.onnx"
)
VOICES_URL = (
    "https://github.com/thewh1teagle/kokoro-onnx/releases/download/"
    "model-files-v1.0/voices-v1.0.bin"
)

app = FastAPI(title="Kokoro TTS Worker")
_pipeline = None
_sample_rate = 24000


class SynthesizeRequest(BaseModel):
    text: str
    voice: str = KOKORO_VOICE


def _split_text(text: str, max_chars: int = KOKORO_MAX_CHARS) -> list[str]:
    cleaned = " ".join(text.split())
    if not cleaned:
        return []
    if len(cleaned) <= max_chars:
        return [cleaned]

    parts: list[str] = []
    current = ""
    for word in cleaned.split():
        candidate = f"{current} {word}".strip() if current else word
        if len(candidate) <= max_chars:
            current = candidate
            continue
        if current:
            parts.append(current)
        if len(word) > max_chars:
            for i in range(0, len(word), max_chars):
                parts.append(word[i : i + max_chars])
            current = ""
        else:
            current = word
    if current:
        parts.append(current)
    return parts


def _ensure_model_files() -> tuple[str, str]:
    model_path = Path(KOKORO_MODEL_PATH)
    voices_path = Path(KOKORO_VOICES_PATH)
    model_path.parent.mkdir(parents=True, exist_ok=True)

    if not model_path.is_file():
        _download_file(MODEL_URL, model_path)
    if not voices_path.is_file():
        _download_file(VOICES_URL, voices_path)

    return str(model_path), str(voices_path)


def _download_file(url: str, dest: Path) -> None:
    import urllib.request

    print(f"Downloading {url} -> {dest}")
    urllib.request.urlretrieve(url, dest)


@app.on_event("startup")
def load_model() -> None:
    global _pipeline
    from kokoro_onnx import Kokoro

    model_path, voices_path = _ensure_model_files()
    _pipeline = Kokoro(model_path, voices_path)


@app.get("/health")
def health() -> dict[str, str | int | bool]:
    return {
        "status": "ok",
        "voice": KOKORO_VOICE,
        "sample_rate": _sample_rate,
        "model_loaded": _pipeline is not None,
        "max_chars": KOKORO_MAX_CHARS,
    }


def _create_audio(text: str, voice: str):
    import numpy as np

    if _pipeline is None:
        return np.array([], dtype=np.float32), _sample_rate

    parts = _split_text(text)
    if not parts:
        return np.array([], dtype=np.float32), _sample_rate

    arrays = []
    rate = _sample_rate
    for part in parts:
        try:
            samples, rate = _pipeline.create(
                part,
                voice=voice,
                speed=1.0,
                lang=KOKORO_LANG,
            )
            arrays.append(np.asarray(samples, dtype=np.float32))
        except (IndexError, ValueError) as exc:
            logger.warning("TTS chunk failed (%s), splitting smaller: %s", exc, part[:80])
            for sub in re.split(r"(?<=[,;])\s+", part):
                sub = sub.strip()
                if not sub:
                    continue
                for tiny in _split_text(sub, max_chars=max(60, KOKORO_MAX_CHARS // 2)):
                    samples, rate = _pipeline.create(
                        tiny,
                        voice=voice,
                        speed=1.0,
                        lang=KOKORO_LANG,
                    )
                    arrays.append(np.asarray(samples, dtype=np.float32))

    if not arrays:
        return np.array([], dtype=np.float32), rate
    return np.concatenate(arrays), rate


@app.post("/synthesize")
async def synthesize(body: SynthesizeRequest) -> StreamingResponse:
    if _pipeline is None:
        raise HTTPException(status_code=503, detail="Model not loaded")

    voice = body.voice or KOKORO_VOICE
    try:
        samples, rate = _create_audio(body.text, voice)
    except Exception as exc:
        logger.exception("Synthesize failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    pcm = _float32_to_pcm16(samples)

    def stream():
        chunk_size = 4096
        for i in range(0, len(pcm), chunk_size):
            yield pcm[i : i + chunk_size]

    return StreamingResponse(
        stream(),
        media_type="application/octet-stream",
        headers={"X-Audio-Sample-Rate": str(rate)},
    )


def _float32_to_pcm16(samples) -> bytes:
    import numpy as np

    arr = np.asarray(samples, dtype=np.float32)
    if arr.size == 0:
        return b""
    arr = np.clip(arr, -1.0, 1.0)
    int16 = (arr * 32767).astype(np.int16)
    return int16.tobytes()
