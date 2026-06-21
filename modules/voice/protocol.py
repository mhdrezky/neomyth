"""WebSocket message protocol for voice sessions."""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class ClientMessageType(StrEnum):
    AUDIO_CHUNK = "audio_chunk"
    SPEECH_START = "speech_start"
    SPEECH_END = "speech_end"
    INTERRUPT = "interrupt"
    PING = "ping"


class ServerMessageType(StrEnum):
    STT_PARTIAL = "stt_partial"
    STT_FINAL = "stt_final"
    LLM_DELTA = "llm_delta"
    TTS_AUDIO = "tts_audio"
    STATE = "state"
    ERROR = "error"
    CONFIG = "config"
    PONG = "pong"


class ClientMessage(BaseModel):
    type: ClientMessageType
    data: dict[str, Any] = Field(default_factory=dict)


class ServerMessage(BaseModel):
    type: ServerMessageType
    data: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def state(cls, phase: str) -> "ServerMessage":
        return cls(type=ServerMessageType.STATE, data={"phase": phase})

    @classmethod
    def error(cls, message: str) -> "ServerMessage":
        return cls(type=ServerMessageType.ERROR, data={"message": message})

    @classmethod
    def stt_final(cls, text: str) -> "ServerMessage":
        return cls(type=ServerMessageType.STT_FINAL, data={"text": text})

    @classmethod
    def llm_delta(cls, text: str) -> "ServerMessage":
        return cls(type=ServerMessageType.LLM_DELTA, data={"text": text})

    @classmethod
    def config(cls, **data: Any) -> "ServerMessage":
        return cls(type=ServerMessageType.CONFIG, data=data)

    @classmethod
    def tts_audio(cls, audio_b64: str, sample_rate: int) -> "ServerMessage":
        return cls(
            type=ServerMessageType.TTS_AUDIO,
            data={"audio": audio_b64, "sample_rate": sample_rate},
        )
