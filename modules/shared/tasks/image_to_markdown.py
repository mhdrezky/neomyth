"""Task: page image (PNG) → markdown transcription via a vision LLM."""

from __future__ import annotations

import re

from modules.shared.clients.vision import VisionLLMClient
from modules.shared.constants import PARSE_LLM_TEMPERATURE, PARSE_VISION_MAX_TOKENS


_FENCE_LINE = re.compile(r"^\s*`{3,}\s*(markdown)?\s*$", re.IGNORECASE)


def _clean_transcription(raw: str) -> str:
    """Drop code-fence wrapper lines; small models loop on them for near-empty
    pages, so a fence-only result collapses to an empty string."""
    lines = [ln for ln in raw.splitlines() if not _FENCE_LINE.match(ln)]
    return "\n".join(lines).strip()


async def image_to_markdown(
    client: VisionLLMClient,
    png: bytes,
    *,
    system_prompt: str,
    user_prompt: str,
    max_tokens: int = PARSE_VISION_MAX_TOKENS,
    temperature: float = PARSE_LLM_TEMPERATURE,
) -> str:
    """Transcribe one page image to markdown. Raises on failure."""
    raw = await client.complete_image(
        system_prompt, user_prompt, png, max_tokens=max_tokens, temperature=temperature
    )
    return _clean_transcription(raw)
