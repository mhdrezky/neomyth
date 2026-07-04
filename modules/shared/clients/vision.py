"""OpenAI-compatible vision chat-completion client (image + text input).

Generic transport wrapper: sends one image as a base64 PNG data URI alongside
a text prompt. Prompt definitions live in each feature module.
"""

from __future__ import annotations

import base64

from openai import AsyncOpenAI


class VisionLLMClient:
    def __init__(self, base_url: str, model: str, api_key: str = "not-needed") -> None:
        self._client = AsyncOpenAI(base_url=base_url, api_key=api_key)
        self._model = model

    async def complete_image(
        self,
        system: str,
        user: str,
        png: bytes,
        *,
        max_tokens: int,
        temperature: float = 0.0,
    ) -> str:
        """One image+text chat call. Raises on failure."""
        data_uri = f"data:image/png;base64,{base64.b64encode(png).decode()}"
        resp = await self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system},
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": data_uri}},
                        {"type": "text", "text": user},
                    ],
                },
            ],
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return (resp.choices[0].message.content or "").strip()

    async def health(self) -> bool:
        try:
            models = await self._client.models.list()
            return len(models.data) > 0
        except Exception:
            return False
