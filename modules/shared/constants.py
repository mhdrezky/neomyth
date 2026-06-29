"""Code-level tunable defaults shared across modules."""

AUDIO_SAMPLE_RATE = 16000
AUDIO_CHANNELS = 1
AUDIO_SAMPLE_WIDTH = 2  # int16

MAX_HISTORY_TURNS = 10
SENTENCE_CHUNK_MIN_CHARS = 40
SENTENCE_END_CHARS = ".?!"

MAX_TTS_CHUNK_CHARS = 150

DEFAULT_LLM_MAX_TOKENS = 256
DEFAULT_LLM_TEMPERATURE = 0.7

# Document parsing LLM budget. The vLLM container exposes a small total context
# window; output is sized dynamically to fit MODEL_MAX_CONTEXT minus the prompt.
MODEL_MAX_CONTEXT = 2048
PARSE_OUTPUT_TOKEN_CAP = 1024
PARSE_MIN_OUTPUT_TOKENS = 256
# Rough chars-per-token used to keep prompt + output within the context window.
CHARS_PER_TOKEN = 3

TARGET_LATENCY_MS = 1200

HTTP_TIMEOUT_SECONDS = 60.0
HTTP_CONNECT_TIMEOUT_SECONDS = 5.0
