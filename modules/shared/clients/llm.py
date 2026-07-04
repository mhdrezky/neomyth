"""OpenAI-compatible text chat-completion client.

Generic transport wrapper for any module. Callers supply their own prompts;
`complete` raises on failure so callers decide the fallback, `complete_json`
swallows errors and returns {} because JSON extraction always has a fallback.
"""

from __future__ import annotations

import json
from typing import Any

from openai import AsyncOpenAI


class TextLLMClient:
    def __init__(self, base_url: str, model: str, api_key: str = "not-needed") -> None:
        self._client = AsyncOpenAI(base_url=base_url, api_key=api_key)
        self._model = model

    async def complete(
        self,
        system: str,
        user: str,
        *,
        max_tokens: int,
        temperature: float = 0.0,
    ) -> str:
        resp = await self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return (resp.choices[0].message.content or "").strip()

    async def complete_json(
        self,
        system: str,
        user: str,
        *,
        max_tokens: int,
        temperature: float = 0.0,
    ) -> dict[str, Any]:
        """JSON-mode chat call. Returns {} on any failure."""
        try:
            resp = await self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                max_tokens=max_tokens,
                temperature=temperature,
                response_format={"type": "json_object"},
            )
            parsed = json.loads(resp.choices[0].message.content or "{}")
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}

    async def health(self) -> bool:
        try:
            models = await self._client.models.list()
            return len(models.data) > 0
        except Exception:
            return False
