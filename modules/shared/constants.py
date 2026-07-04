"""Code-level tunable defaults shared across modules."""

AUDIO_SAMPLE_RATE = 16000
AUDIO_CHANNELS = 1
AUDIO_SAMPLE_WIDTH = 2  # int16

MAX_HISTORY_TURNS = 10
SENTENCE_CHUNK_MIN_CHARS = 40
SENTENCE_END_CHARS = ".?!"

MAX_TTS_CHUNK_CHARS = 150

DEFAULT_LLM_MAX_TOKENS = 256

# Per-module LLM temperatures. Not runtime env: each module has a fixed need —
# voice wants natural conversation, parse wants deterministic extraction.
VOICE_LLM_TEMPERATURE = 0.7
PARSE_LLM_TEMPERATURE = 0.0

# Document parsing LLM budget. Must not exceed the vLLM worker's
# --max-model-len (deploy/vllm-llm/.env LLM_MAX_MODEL_LEN); 8192 is what a
# 4GB GPU fits for this model. Output is sized dynamically minus the prompt.
MODEL_MAX_CONTEXT = 8192
# Minimum output reserve for markdown → JSON extraction. The document body is
# truncated to always leave at least this much; the actual max_tokens per call
# is dynamic — the whole window left over after the prompt.
PARSE_OUTPUT_RESERVE_TOKENS = 2048
# Rough chars-per-token used to keep prompt + output within the context window.
CHARS_PER_TOKEN = 3

# Parse routing: a page with fewer extractable characters than this is treated
# as a scanned image and sent to the vision model instead of PyMuPDF text.
PARSE_SCANNED_PAGE_MIN_CHARS = 64
PARSE_VISION_MAX_TOKENS = 4096
PARSE_VISION_RENDER_ZOOM = 2.0
# How many times to ask the LLM to fix JSON that fails draft-07 validation.
PARSE_JSON_REPAIR_ATTEMPTS = 1

TARGET_LATENCY_MS = 1200

HTTP_TIMEOUT_SECONDS = 60.0
HTTP_CONNECT_TIMEOUT_SECONDS = 5.0
