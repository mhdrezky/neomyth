"""LangGraph voice turn pipeline — STT → LLM → TTS with session memory."""

from __future__ import annotations

import asyncio
import base64
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Literal, TypedDict

from langgraph.checkpoint.memory import MemorySaver
from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph
from langchain_core.runnables import RunnableConfig

from modules.shared.constants import MAX_HISTORY_TURNS
from modules.shared.types import Phase
from modules.shared.utils.text import SentenceChunker, clean_text_for_tts, trim_message_history
from modules.voice.clients.llm import LLMClient
from modules.voice.clients.stt import STTClient
from modules.voice.clients.tts import TTSClient

VOICE_SYSTEM_PROMPT = (
    "You are a helpful voice assistant. Reply in the same language the user speaks. "
    "Your reply will be read aloud by text-to-speech. Use plain spoken sentences only. "
    "Never use markdown, asterisks, bold, bullet lists, numbered lists, headers, or code. "
    "No symbols like * # _ ` or **. Keep replies short and conversational."
)


class VoiceGraphState(TypedDict, total=False):
    messages: list[dict[str, str]]
    phase: str
    turn_id: int
    pcm_audio: bytes
    transcript: str
    assistant_text: str
    error: str | None


StreamEvent = dict[str, Any]


@dataclass
class VoiceGraphRuntime:
    """Mutable runtime deps injected into graph nodes via configurable."""

    stt: STTClient
    llm: LLMClient
    tts: TTSClient
    cancel_event: asyncio.Event = field(default_factory=asyncio.Event)
    generation_id: int = 0

    def is_stale(self, gen: int) -> bool:
        return gen != self.generation_id or self.cancel_event.is_set()


def _initial_messages() -> list[dict[str, str]]:
    return [{"role": "system", "content": VOICE_SYSTEM_PROMPT}]


def _ensure_messages(messages: list[dict[str, str]] | None) -> list[dict[str, str]]:
    if not messages:
        return _initial_messages()
    return messages


def _append_user(messages: list[dict[str, str]], text: str) -> list[dict[str, str]]:
    updated = [*messages, {"role": "user", "content": text}]
    return trim_message_history(updated, MAX_HISTORY_TURNS)


def _append_assistant(messages: list[dict[str, str]], text: str) -> list[dict[str, str]]:
    updated = [*messages, {"role": "assistant", "content": text}]
    return trim_message_history(updated, MAX_HISTORY_TURNS)


def _runtime(config: RunnableConfig) -> VoiceGraphRuntime:
    configurable = config.get("configurable") or {}
    return configurable["runtime"]


async def _emit_tts(
    runtime: VoiceGraphRuntime,
    sentence: str,
    gen: int,
    writer: Any,
) -> None:
    spoken = clean_text_for_tts(sentence)
    if not spoken:
        return
    writer({"type": "state", "phase": Phase.SPEAKING.value})
    async for chunk, sample_rate in runtime.tts.synthesize(
        spoken,
        cancel_event=runtime.cancel_event,
    ):
        if runtime.is_stale(gen):
            return
        writer(
            {
                "type": "tts_audio",
                "audio": base64.b64encode(chunk).decode("ascii"),
                "sample_rate": sample_rate,
            }
        )


async def transcribe_node(
    state: VoiceGraphState,
    config: RunnableConfig,
) -> VoiceGraphState:
    runtime = _runtime(config)
    writer = get_stream_writer()
    gen = runtime.generation_id

    pcm = state.get("pcm_audio", b"")
    messages = _ensure_messages(state.get("messages"))
    turn_id = state.get("turn_id", 0)

    writer({"type": "state", "phase": Phase.THINKING.value})

    transcript = await runtime.stt.transcribe(pcm)
    if runtime.is_stale(gen):
        return {"phase": Phase.LISTENING.value, "messages": messages, "turn_id": turn_id}

    if not transcript:
        writer({"type": "state", "phase": Phase.LISTENING.value})
        return {
            "messages": messages,
            "phase": Phase.LISTENING.value,
            "turn_id": turn_id,
            "transcript": "",
        }

    writer({"type": "stt_final", "text": transcript})
    messages = _append_user(messages, transcript)

    return {
        "messages": messages,
        "transcript": transcript,
        "phase": Phase.THINKING.value,
        "turn_id": turn_id + 1,
    }


def _route_after_transcribe(state: VoiceGraphState) -> Literal["generate_and_speak", "__end__"]:
    if state.get("transcript"):
        return "generate_and_speak"
    return END


async def generate_and_speak_node(
    state: VoiceGraphState,
    config: RunnableConfig,
) -> VoiceGraphState:
    runtime = _runtime(config)
    writer = get_stream_writer()
    gen = runtime.generation_id

    messages = _ensure_messages(state.get("messages"))
    assistant_text = ""
    chunker = SentenceChunker()

    async for token in runtime.llm.stream_chat(
        messages,
        cancel_event=runtime.cancel_event,
    ):
        if runtime.is_stale(gen):
            return {"messages": messages, "phase": Phase.LISTENING.value}
        assistant_text += token
        writer({"type": "llm_delta", "text": token})
        for sentence in chunker.push(token):
            await _emit_tts(runtime, sentence, gen, writer)

    for sentence in chunker.flush():
        if runtime.is_stale(gen):
            return {"messages": messages, "phase": Phase.LISTENING.value}
        await _emit_tts(runtime, sentence, gen, writer)

    if assistant_text.strip():
        messages = _append_assistant(messages, clean_text_for_tts(assistant_text))

    if not runtime.is_stale(gen):
        writer({"type": "state", "phase": Phase.LISTENING.value})

    return {
        "messages": messages,
        "assistant_text": assistant_text,
        "phase": Phase.LISTENING.value,
        "turn_id": state.get("turn_id", 0),
    }


def build_voice_graph() -> StateGraph:
    graph = StateGraph(VoiceGraphState)
    graph.add_node("transcribe", transcribe_node)
    graph.add_node("generate_and_speak", generate_and_speak_node)
    graph.add_edge(START, "transcribe")
    graph.add_conditional_edges("transcribe", _route_after_transcribe)
    graph.add_edge("generate_and_speak", END)
    return graph


class VoiceGraphSession:
    """Per-session LangGraph runner with in-memory checkpoint (conversation memory)."""

    def __init__(self, runtime: VoiceGraphRuntime, thread_id: str) -> None:
        self._runtime = runtime
        self._thread_id = thread_id
        self._checkpointer = MemorySaver()
        self._graph = build_voice_graph().compile(checkpointer=self._checkpointer)
        self._bootstrap_state()

    @property
    def phase(self) -> Phase:
        snapshot = self._graph.get_state(self._config())
        value = snapshot.values.get("phase", Phase.IDLE.value)
        try:
            return Phase(value)
        except ValueError:
            return Phase.IDLE

    @property
    def messages(self) -> list[dict[str, str]]:
        snapshot = self._graph.get_state(self._config())
        return list(snapshot.values.get("messages") or _initial_messages())

    def _config(self) -> dict[str, Any]:
        return {"configurable": {"thread_id": self._thread_id, "runtime": self._runtime}}

    def _bootstrap_state(self) -> None:
        snapshot = self._graph.get_state(self._config())
        if snapshot.values.get("messages"):
            return
        self._graph.update_state(
            self._config(),
            {
                "messages": _initial_messages(),
                "phase": Phase.LISTENING.value,
                "turn_id": 0,
            },
        )

    def set_phase(self, phase: Phase) -> None:
        self._graph.update_state(self._config(), {"phase": phase.value})

    async def run_turn(self, pcm_audio: bytes) -> AsyncIterator[StreamEvent]:
        """Stream custom pipeline events via LangGraph stream_mode='custom'."""
        prior = self._graph.get_state(self._config()).values
        async for event in self._graph.astream(
            {
                "pcm_audio": pcm_audio,
                "messages": prior.get("messages") or _initial_messages(),
                "turn_id": prior.get("turn_id", 0),
            },
            config=self._config(),
            stream_mode="custom",
        ):
            yield event

    async def run_debug(self, pcm_audio: bytes) -> dict[str, str]:
        """Non-streaming STT → LLM for HTTP debug endpoint."""
        transcript = await self._runtime.stt.transcribe(pcm_audio)
        messages = _append_user(self.messages, transcript)
        parts: list[str] = []
        async for token in self._runtime.llm.stream_chat(messages):
            parts.append(token)
        reply = "".join(parts).strip()
        cleaned = clean_text_for_tts(reply)
        self._graph.update_state(
            self._config(),
            {
                "messages": _append_assistant(messages, cleaned),
                "phase": Phase.LISTENING.value,
            },
        )
        return {"transcript": transcript, "reply": cleaned}
