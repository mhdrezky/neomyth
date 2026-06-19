"""OpenAI-compatible client for the vLLM LLM worker."""

import asyncio
from collections.abc import AsyncIterator

from openai import AsyncOpenAI

from modules.shared.constants import DEFAULT_LLM_MAX_TOKENS, DEFAULT_LLM_TEMPERATURE


class LLMClient:
    def __init__(
        self,
        base_url: str,
        model: str,
        max_tokens: int = DEFAULT_LLM_MAX_TOKENS,
        temperature: float = DEFAULT_LLM_TEMPERATURE,
    ) -> None:
        self._client = AsyncOpenAI(base_url=base_url, api_key="not-needed")
        self._model = model
        self._max_tokens = max_tokens
        self._temperature = temperature

    async def stream_chat(
        self,
        messages: list[dict[str, str]],
        cancel_event: asyncio.Event | None = None,
    ) -> AsyncIterator[str]:
        stream = await self._client.chat.completions.create(
            model=self._model,
            messages=messages,  # type: ignore[arg-type]
            max_tokens=self._max_tokens,
            temperature=self._temperature,
            stream=True,
        )
        try:
            async for chunk in stream:
                if cancel_event and cancel_event.is_set():
                    break
                delta = chunk.choices[0].delta.content
                if delta:
                    yield delta
        finally:
            await stream.close()

    async def health(self) -> bool:
        try:
            models = await self._client.models.list()
            return len(models.data) > 0
        except Exception:
            return False
