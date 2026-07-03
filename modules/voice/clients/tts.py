"""HTTP client for the Kokoro TTS worker."""

import asyncio
from collections.abc import AsyncIterator

import httpx

DEFAULT_TTS_SAMPLE_RATE = 24000


class TTSClient:
    def __init__(
        self,
        base_url: str,
        http_client: httpx.AsyncClient,
        voice: str = "af_sarah",
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._http = http_client
        self._voice = voice

    async def synthesize(
        self,
        text: str,
        cancel_event: asyncio.Event | None = None,
    ) -> AsyncIterator[tuple[bytes, int]]:
        async with self._http.stream(
            "POST",
            f"{self._base_url}/synthesize",
            json={"text": text, "voice": self._voice},
        ) as response:
            response.raise_for_status()
            sample_rate = int(
                response.headers.get("X-Audio-Sample-Rate", DEFAULT_TTS_SAMPLE_RATE)
            )
            # Network chunk boundaries are arbitrary; carry any odd trailing
            # byte so every yielded chunk stays aligned to int16 samples.
            pending = b""
            async for chunk in response.aiter_bytes():
                if cancel_event and cancel_event.is_set():
                    break
                if not chunk:
                    continue
                data = pending + chunk
                if len(data) % 2:
                    pending = data[-1:]
                    data = data[:-1]
                else:
                    pending = b""
                if data:
                    yield data, sample_rate

    async def health(self) -> bool:
        try:
            response = await self._http.get(f"{self._base_url}/health")
            return response.status_code == 200
        except httpx.HTTPError:
            return False
