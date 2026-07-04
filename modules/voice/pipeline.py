"""Voice pipeline orchestrating STT → LLM → TTS with cancellation."""

import asyncio
import uuid
from collections.abc import AsyncIterator

from modules.shared.constants import VOICE_LLM_TEMPERATURE
from modules.shared.types import Phase, PipelineEvent, PipelineEventType
from modules.shared.utils.http import create_async_client
from modules.voice.clients.llm import LLMClient
from modules.voice.clients.stt import STTClient
from modules.voice.clients.tts import TTSClient
from modules.voice.graph import VoiceGraphRuntime, VoiceGraphSession


class VoicePipeline:
    def __init__(
        self,
        stt_base_url: str,
        llm_base_url: str,
        llm_model: str,
        tts_base_url: str,
        tts_voice: str = "af_sarah",
        llm_max_tokens: int = 256,
        llm_temperature: float = VOICE_LLM_TEMPERATURE,
    ) -> None:
        self._http = create_async_client()
        self._runtime = VoiceGraphRuntime(
            stt=STTClient(stt_base_url, self._http),
            llm=LLMClient(
                llm_base_url,
                llm_model,
                max_tokens=llm_max_tokens,
                temperature=llm_temperature,
            ),
            tts=TTSClient(tts_base_url, self._http, voice=tts_voice),
        )
        self._session = VoiceGraphSession(self._runtime, thread_id=str(uuid.uuid4()))
        self._generation_id = 0

    @property
    def phase(self) -> Phase:
        return self._session.phase

    def set_listening(self) -> PipelineEvent:
        self._session.set_phase(Phase.LISTENING)
        return PipelineEvent(
            type=PipelineEventType.STATE,
            data={"phase": Phase.LISTENING.value},
        )

    def cancel(self) -> None:
        self._generation_id += 1
        self._runtime.generation_id = self._generation_id
        self._runtime.cancel_event.set()
        self._session.set_phase(Phase.LISTENING)

    async def close(self) -> None:
        self.cancel()
        await self._http.aclose()

    async def handle_speech_end(self, pcm_audio: bytes) -> AsyncIterator[PipelineEvent]:
        self.cancel()
        self._runtime.cancel_event = asyncio.Event()
        gen = self._generation_id

        try:
            async for event in self._session.run_turn(pcm_audio):
                if gen != self._generation_id:
                    return
                yield _stream_event_to_pipeline(event)
        except asyncio.CancelledError:
            return
        except Exception as exc:
            if gen == self._generation_id:
                yield PipelineEvent(
                    type=PipelineEventType.ERROR,
                    data={
                        "message": str(exc),
                        "phase": self._session.phase.value,
                    },
                )
                self._session.set_phase(Phase.LISTENING)
                yield PipelineEvent(
                    type=PipelineEventType.STATE,
                    data={"phase": Phase.LISTENING.value},
                )

    async def workers_health(self) -> dict[str, bool]:
        stt_ok, llm_ok, tts_ok = await asyncio.gather(
            self._runtime.stt.health(),
            self._runtime.llm.health(),
            self._runtime.tts.health(),
        )
        return {"stt": stt_ok, "llm": llm_ok, "tts": tts_ok}

    async def debug_chain(self, pcm_audio: bytes) -> dict[str, str]:
        """Debug helper for HTTP testing without WebSocket."""
        return await self._session.run_debug(pcm_audio)


def _stream_event_to_pipeline(event: dict) -> PipelineEvent:
    event_type = event.get("type", "")
    mapping = {
        "stt_final": PipelineEventType.STT_FINAL,
        "llm_delta": PipelineEventType.LLM_DELTA,
        "tts_audio": PipelineEventType.TTS_AUDIO,
        "state": PipelineEventType.STATE,
        "error": PipelineEventType.ERROR,
    }
    pipeline_type = mapping.get(event_type, PipelineEventType.STATE)
    if event_type == "stt_final":
        data = {"text": event.get("text", "")}
    elif event_type == "llm_delta":
        data = {"text": event.get("text", "")}
    elif event_type == "tts_audio":
        data = {"audio": event.get("audio", ""), "sample_rate": event.get("sample_rate", 16000)}
    elif event_type == "state":
        data = {"phase": event.get("phase", "idle")}
    elif event_type == "error":
        data = {"message": event.get("message", "Unknown error")}
    else:
        data = dict(event)
    return PipelineEvent(type=pipeline_type, data=data)
