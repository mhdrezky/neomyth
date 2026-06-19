"""Shared types used across AI modules."""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class Phase(StrEnum):
    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"


class PipelineEventType(StrEnum):
    STT_FINAL = "stt_final"
    LLM_DELTA = "llm_delta"
    TTS_AUDIO = "tts_audio"
    STATE = "state"
    ERROR = "error"


class PipelineEvent(BaseModel):
    type: PipelineEventType
    data: dict[str, Any] = Field(default_factory=dict)
