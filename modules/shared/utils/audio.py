"""PCM / WAV audio helpers."""

import io
import struct
import wave

from modules.shared.constants import (
    AUDIO_CHANNELS,
    AUDIO_SAMPLE_RATE,
    AUDIO_SAMPLE_WIDTH,
)


def pcm_to_wav(pcm: bytes, sample_rate: int = AUDIO_SAMPLE_RATE) -> bytes:
    """Wrap raw int16 PCM mono bytes in a WAV container."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(AUDIO_CHANNELS)
        wf.setsampwidth(AUDIO_SAMPLE_WIDTH)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm)
    return buf.getvalue()


def wav_duration_seconds(wav_bytes: bytes) -> float:
    """Return duration of a WAV byte buffer in seconds."""
    with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
        return wf.getnframes() / float(wf.getframerate())


def int16_bytes_to_float32(pcm: bytes) -> list[float]:
    """Convert int16 PCM bytes to normalized float32 samples."""
    count = len(pcm) // 2
    samples = struct.unpack(f"<{count}h", pcm)
    return [s / 32768.0 for s in samples]
