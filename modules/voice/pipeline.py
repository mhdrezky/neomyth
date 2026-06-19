"""Voice pipeline orchestrating STT → LLM → TTS with cancellation."""

import asyncio
import base64
from collections.abc import AsyncIterator

from modules.shared.types import Phase, PipelineEvent, PipelineEventType
from modules.shared.utils.http import create_async_client
from modules.shared.utils.text import SentenceChunker
from modules.voice.clients.llm import LLMClient
from modules.voice.clients.stt import STTClient
from modules.voice.clients.tts import TTSClient
from modules.voice.graph import ConversationState


class VoicePipeline:
    def __init__(
        self,
        stt_base_url: str,
        llm_base_url: str,
        llm_model: str,
        tts_base_url: str,
        tts_voice: str = "af_sarah",
        llm_max_tokens: int = 256,
        llm_temperature: float = 0.7,
    ) -> None:
        self._http = create_async_client()
        self._stt = STTClient(stt_base_url, self._http)
        self._llm = LLMClient(
            llm_base_url,
            llm_model,
            max_tokens=llm_max_tokens,
            temperature=llm_temperature,
        )
        self._tts = TTSClient(tts_base_url, self._http, voice=tts_voice)
        self._state = ConversationState()
        self._generation_id = 0
        self._cancel_event = asyncio.Event()

    @property
    def phase(self) -> Phase:
        return self._state.phase

    def set_listening(self) -> PipelineEvent:
        self._state.set_phase(Phase.LISTENING)
        return PipelineEvent(
            type=PipelineEventType.STATE,
            data={"phase": Phase.LISTENING.value},
        )

    def cancel(self) -> None:
        self._generation_id += 1
        self._cancel_event.set()
        self._state.set_phase(Phase.LISTENING)

    async def close(self) -> None:
        self.cancel()
        await self._http.aclose()

    async def handle_speech_end(self, pcm_audio: bytes) -> AsyncIterator[PipelineEvent]:
        self.cancel()
        self._cancel_event = asyncio.Event()
        gen = self._generation_id

        try:
            self._state.set_phase(Phase.THINKING)
            yield PipelineEvent(
                type=PipelineEventType.STATE,
                data={"phase": Phase.THINKING.value},
            )

            transcript = await self._stt.transcribe(pcm_audio)
            if gen != self._generation_id:
                return
            if not transcript:
                self._state.set_phase(Phase.LISTENING)
                yield PipelineEvent(
                    type=PipelineEventType.STATE,
                    data={"phase": Phase.LISTENING.value},
                )
                return

            yield PipelineEvent(
                type=PipelineEventType.STT_FINAL,
                data={"text": transcript},
            )

            self._state.append_user(transcript)
            assistant_text = ""
            chunker = SentenceChunker()

            async for token in self._llm.stream_chat(
                self._state.chat_messages(),
                cancel_event=self._cancel_event,
            ):
                if gen != self._generation_id or self._cancel_event.is_set():
                    return
                assistant_text += token
                yield PipelineEvent(
                    type=PipelineEventType.LLM_DELTA,
                    data={"text": token},
                )
                for sentence in chunker.push(token):
                    async for event in self._speak_sentence(sentence, gen):
                        yield event

            for sentence in chunker.flush():
                async for event in self._speak_sentence(sentence, gen):
                    yield event

            if assistant_text.strip():
                self._state.append_assistant(assistant_text.strip())

            if gen == self._generation_id:
                self._state.set_phase(Phase.LISTENING)
                yield PipelineEvent(
                    type=PipelineEventType.STATE,
                    data={"phase": Phase.LISTENING.value},
                )
        except asyncio.CancelledError:
            return
        except Exception as exc:
            if gen == self._generation_id:
                yield PipelineEvent(
                    type=PipelineEventType.ERROR,
                    data={
                        "message": str(exc),
                        "phase": self._state.phase.value,
                    },
                )
                self._state.set_phase(Phase.LISTENING)
                yield PipelineEvent(
                    type=PipelineEventType.STATE,
                    data={"phase": Phase.LISTENING.value},
                )

    async def _speak_sentence(
        self,
        sentence: str,
        generation_id: int,
    ) -> AsyncIterator[PipelineEvent]:
        if generation_id != self._generation_id:
            return
        self._state.set_phase(Phase.SPEAKING)
        yield PipelineEvent(
            type=PipelineEventType.STATE,
            data={"phase": Phase.SPEAKING.value},
        )
        async for chunk, sample_rate in self._tts.synthesize(
            sentence,
            cancel_event=self._cancel_event,
        ):
            if generation_id != self._generation_id or self._cancel_event.is_set():
                return
            yield PipelineEvent(
                type=PipelineEventType.TTS_AUDIO,
                data={
                    "audio": base64.b64encode(chunk).decode("ascii"),
                    "sample_rate": sample_rate,
                },
            )

    async def workers_health(self) -> dict[str, bool]:
        stt_ok, llm_ok, tts_ok = await asyncio.gather(
            self._stt.health(),
            self._llm.health(),
            self._tts.health(),
        )
        return {"stt": stt_ok, "llm": llm_ok, "tts": tts_ok}

    async def debug_chain(self, pcm_audio: bytes) -> dict[str, str]:
        """Debug helper for HTTP testing without WebSocket."""
        transcript = await self._stt.transcribe(pcm_audio)
        self._state.append_user(transcript)
        parts: list[str] = []
        async for token in self._llm.stream_chat(self._state.chat_messages()):
            parts.append(token)
        reply = "".join(parts).strip()
        self._state.append_assistant(reply)
        return {"transcript": transcript, "reply": reply}
