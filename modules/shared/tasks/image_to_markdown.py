"""Task: page image (PNG) → markdown transcription via a vision LLM."""

from __future__ import annotations

from modules.shared.clients.vision import VisionLLMClient
from modules.shared.constants import PARSE_LLM_TEMPERATURE, PARSE_VISION_MAX_TOKENS


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
    return await client.complete_image(
        system_prompt, user_prompt, png, max_tokens=max_tokens, temperature=temperature
    )
