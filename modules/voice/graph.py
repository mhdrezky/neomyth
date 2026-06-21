"""Conversation graph and state for voice sessions."""

from dataclasses import dataclass, field

from modules.shared.constants import MAX_HISTORY_TURNS
from modules.shared.types import Phase
from modules.shared.utils.text import trim_message_history

VOICE_SYSTEM_PROMPT = (
    "You are a helpful voice assistant. Reply in the same language the user speaks. "
    "Your reply will be read aloud by text-to-speech. Use plain spoken sentences only. "
    "Never use markdown, asterisks, bold, bullet lists, numbered lists, headers, or code. "
    "No symbols like * # _ ` or **. Keep replies short and conversational."
)


@dataclass
class ConversationState:
    messages: list[dict[str, str]] = field(default_factory=list)
    phase: Phase = Phase.IDLE
    turn_id: int = 0

    def __post_init__(self) -> None:
        if not self.messages:
            self.messages = [{"role": "system", "content": VOICE_SYSTEM_PROMPT}]

    def set_phase(self, phase: Phase) -> None:
        self.phase = phase

    def append_user(self, text: str) -> None:
        self.messages.append({"role": "user", "content": text})
        self.messages = trim_message_history(self.messages, MAX_HISTORY_TURNS)
        self.turn_id += 1

    def append_assistant(self, text: str) -> None:
        self.messages.append({"role": "assistant", "content": text})
        self.messages = trim_message_history(self.messages, MAX_HISTORY_TURNS)

    def chat_messages(self) -> list[dict[str, str]]:
        return list(self.messages)
