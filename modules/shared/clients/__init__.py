"""Reusable OpenAI-compatible LLM clients (text and vision).

Transport only — prompt definitions live in each feature module.
"""

from modules.shared.clients.llm import TextLLMClient
from modules.shared.clients.vision import VisionLLMClient

__all__ = ["TextLLMClient", "VisionLLMClient"]
