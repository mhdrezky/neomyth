"""Official hexgrad/Kokoro-82M TTS worker (PyTorch)."""

import logging
import os
import re

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Kokoro lang_code: a=American en, b=British, e=es, f=fr, h=hi, i=it, j=ja, p=pt-br, z=zh
# See https://huggingface.co/hexgrad/Kokoro-82M/blob/main/VOICES.md
KOKORO_LANG_CODE = os.getenv("KOKORO_LANG_CODE", "a")
KOKORO_VOICE = os.getenv("KOKORO_VOICE", "af_sarah")
KOKORO_MAX_CHARS = int(os.getenv("KOKORO_MAX_CHARS", "150"))
KOKORO_MODEL_ID = "hexgrad/Kokoro-82M"

app = FastAPI(title="Kokoro TTS Worker (hexgrad)")
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


def _synthesize_part(text: str, voice: str):
    import numpy as np

    chunks: list[np.ndarray] = []
    for _gs, _ps, audio in _pipeline(text, voice=voice):
        chunks.append(np.asarray(audio, dtype=np.float32))
    if not chunks:
        return np.array([], dtype=np.float32)
    return np.concatenate(chunks)


@app.on_event("startup")
def load_model() -> None:
    global _pipeline
    from kokoro import KPipeline

    logger.info(
        "Loading %s lang_code=%s voice=%s",
        KOKORO_MODEL_ID,
        KOKORO_LANG_CODE,
        KOKORO_VOICE,
    )
    _pipeline = KPipeline(lang_code=KOKORO_LANG_CODE)
    # Warm-up: triggers Hugging Face weight download on first start.
    list(_pipeline("Ready.", voice=KOKORO_VOICE))
    logger.info("Kokoro pipeline ready")


@app.get("/health")
def health() -> dict[str, str | int | bool]:
    return {
        "status": "ok",
        "backend": "hexgrad/kokoro",
        "model": KOKORO_MODEL_ID,
        "lang_code": KOKORO_LANG_CODE,
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

    arrays: list[np.ndarray] = []
    for part in parts:
        try:
            arrays.append(_synthesize_part(part, voice))
        except Exception as exc:
            logger.warning("TTS chunk failed (%s), splitting smaller: %s", exc, part[:80])
            for sub in re.split(r"(?<=[,;])\s+", part):
                sub = sub.strip()
                if not sub:
                    continue
                for tiny in _split_text(sub, max_chars=max(60, KOKORO_MAX_CHARS // 2)):
                    arrays.append(_synthesize_part(tiny, voice))

    if not arrays:
        return np.array([], dtype=np.float32), _sample_rate
    return np.concatenate(arrays), _sample_rate


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
