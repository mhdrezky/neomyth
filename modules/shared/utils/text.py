"""Text processing helpers for streaming pipelines."""

import re

from modules.shared.constants import (
    MAX_HISTORY_TURNS,
    MAX_TTS_CHUNK_CHARS,
    SENTENCE_CHUNK_MIN_CHARS,
    SENTENCE_END_CHARS,
)


def trim_message_history(
    messages: list[dict[str, str]],
    max_turns: int = MAX_HISTORY_TURNS,
) -> list[dict[str, str]]:
    """Keep system prompt plus the most recent user/assistant turns."""
    if not messages:
        return []

    system = [m for m in messages if m.get("role") == "system"]
    rest = [m for m in messages if m.get("role") != "system"]
    max_messages = max_turns * 2
    if len(rest) > max_messages:
        rest = rest[-max_messages:]
    return system + rest


def clean_text_for_tts(text: str) -> str:
    """Strip markdown so TTS does not speak asterisks, hashes, or list markers."""
    if not text.strip():
        return ""

    t = text
    t = re.sub(r"```[\s\S]*?```", " ", t)
    t = re.sub(r"`([^`]+)`", r"\1", t)
    t = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", t)
    t = re.sub(r"\*\*([^*]+)\*\*", r"\1", t)
    t = re.sub(r"__([^_]+)__", r"\1", t)
    t = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"\1", t)
    t = re.sub(r"(?<!_)_([^_\n]+)_(?!_)", r"\1", t)
    t = re.sub(r"^#{1,6}\s*", "", t, flags=re.MULTILINE)
    t = re.sub(r"^\s*[-*+]\s+", "", t, flags=re.MULTILINE)
    t = re.sub(r"^\s*\d+[.)]\s+", "", t, flags=re.MULTILINE)
    t = t.replace("*", " ").replace("#", " ").replace("_", " ")
    t = re.sub(r"\s+", " ", t).strip()
    return t


def split_text_for_tts(
    text: str,
    max_chars: int = MAX_TTS_CHUNK_CHARS,
) -> list[str]:
    """Split text into Kokoro-safe chunks (avoids 510-phoneme limit)."""
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


def _split_long_chunk(chunk: str, max_chars: int = MAX_TTS_CHUNK_CHARS) -> list[str]:
    if len(chunk) <= max_chars:
        return [chunk] if chunk.strip() else []
    segments = re.split(r"([.?!]+)", chunk)
    merged: list[str] = []
    buf = ""
    for seg in segments:
        if not seg:
            continue
        candidate = f"{buf}{seg}".strip()
        if len(candidate) <= max_chars:
            buf = candidate if candidate.endswith((".", "?", "!")) else f"{candidate} "
            continue
        if buf.strip():
            merged.extend(split_text_for_tts(buf.strip(), max_chars))
        buf = seg if seg in ".?!" else seg
    if buf.strip():
        merged.extend(split_text_for_tts(buf.strip(), max_chars))
    return merged or split_text_for_tts(chunk, max_chars)


class SentenceChunker:
    """Buffer streaming LLM tokens and emit speakable sentence chunks."""

    def __init__(
        self,
        min_chars: int = SENTENCE_CHUNK_MIN_CHARS,
        end_chars: str = SENTENCE_END_CHARS,
    ) -> None:
        self._buffer = ""
        self._min_chars = min_chars
        self._end_chars = end_chars

    def push(self, token: str) -> list[str]:
        self._buffer += token
        return self._drain(force=False)

    def flush(self) -> list[str]:
        return self._drain(force=True)

    def _drain(self, force: bool) -> list[str]:
        chunks: list[str] = []
        while True:
            if not self._buffer:
                break
            end_idx = -1
            for i, ch in enumerate(self._buffer):
                if ch in self._end_chars and i + 1 >= self._min_chars:
                    end_idx = i
                    break
            if end_idx >= 0:
                chunk = self._buffer[: end_idx + 1].strip()
                self._buffer = self._buffer[end_idx + 1 :].lstrip()
                if chunk:
                    chunks.extend(_split_long_chunk(chunk))
                continue
            if force and len(self._buffer.strip()) >= self._min_chars:
                chunk = self._buffer.strip()
                self._buffer = ""
                chunks.extend(_split_long_chunk(chunk))
            break
        return chunks
