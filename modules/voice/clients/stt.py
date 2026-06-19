"""HTTP client for the Faster-Whisper STT worker."""

import httpx

from modules.shared.utils.audio import pcm_to_wav


class STTClient:
    def __init__(self, base_url: str, http_client: httpx.AsyncClient) -> None:
        self._base_url = base_url.rstrip("/")
        self._http = http_client

    async def transcribe(self, pcm_audio: bytes) -> str:
        wav = pcm_to_wav(pcm_audio)
        response = await self._http.post(
            f"{self._base_url}/transcribe",
            content=wav,
            headers={"Content-Type": "audio/wav"},
        )
        response.raise_for_status()
        payload = response.json()
        return str(payload.get("text", "")).strip()

    async def health(self) -> bool:
        try:
            response = await self._http.get(f"{self._base_url}/health")
            return response.status_code == 200
        except httpx.HTTPError:
            return False
