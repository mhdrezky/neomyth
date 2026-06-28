"""Runtime configuration from environment variables."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

from modules.shared.constants import DEFAULT_LLM_MAX_TOKENS, DEFAULT_LLM_TEMPERATURE


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    api_host: str = "0.0.0.0"
    api_port: int = 5000

    cors_origins: list[str] = ["http://localhost:4321"]

    vllm_base_url: str = "http://localhost:5001/v1"
    vllm_model: str = "qwen-3.5"
    vllm_max_tokens: int = DEFAULT_LLM_MAX_TOKENS
    vllm_temperature: float = DEFAULT_LLM_TEMPERATURE

    stt_base_url: str = "http://localhost:5002"
    tts_base_url: str = "http://localhost:5003"
    tts_voice: str = "af_sarah"

    # Smart interruption (barge-in while AI speaks). Default off.
    voice_interrupt_enabled: bool = False

    # PostgreSQL
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/neomyth"


@lru_cache
def get_settings() -> Settings:
    return Settings()
