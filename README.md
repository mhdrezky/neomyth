# Neomyth

Multi-module AI monorepo with a centralized FastAPI gateway and Docker inference workers.

## Architecture

```text
Browser  →  api/ (FastAPI)  →  modules/voice/ (orchestration)
                                    ↓
              deploy/vllm-llm · whisper-stt · kokoro-tts (workers)
```

| Layer | Path | Role |
|-------|------|------|
| Gateway | `api/` | HTTP, WebSocket, UI |
| Core AI | `modules/voice/` | Pipeline, graph, worker clients |
| Shared | `modules/shared/` | Constants, utils |
| Workers | `deploy/*/` | STT, LLM, TTS inference |

See [AGENTS.md](AGENTS.md) for agent/developer conventions and [docs/neomyth-voice/architecture.md](docs/neomyth-voice/architecture.md) for the voice pipeline.

## Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- Docker with NVIDIA GPU support (recommended)
- Microphone + speakers for voice UI

## Quick start

### 1. Workers

```bash
# LLM (existing)
cd deploy/vllm-llm
cp .env.example .env   # if needed
docker compose up -d

# STT + TTS
cd ../whisper-stt && cp .env.example .env && docker compose up -d
cd ../kokoro-tts && cp .env.example .env && docker compose up -d
```

Or orchestrate all workers:

```bash
cd deploy
cp vllm-llm/.env.example vllm-llm/.env
cp whisper-stt/.env.example whisper-stt/.env
cp kokoro-tts/.env.example kokoro-tts/.env
docker compose --profile workers up -d
```

### 2. API (local)

```bash
cp .env.example .env
uv sync
uv run uvicorn api.main:app --host 0.0.0.0 --port 8080 --reload
```

Open **http://localhost:8080/voice**

### 3. Full Docker stack

```bash
cd deploy
docker compose --profile full up -d
```

## Environment

Root `.env.example` — API and worker URLs for local dev:

| Variable | Default | Description |
|----------|---------|-------------|
| `VLLM_BASE_URL` | `http://localhost:5001/v1` | vLLM OpenAI API |
| `VLLM_MODEL` | `qwen-3.5` | Served model name |
| `STT_BASE_URL` | `http://localhost:5002` | Whisper worker |
| `TTS_BASE_URL` | `http://localhost:5003` | Kokoro worker |

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | API health |
| GET | `/voice` | Voice test UI |
| GET | `/voice/health` | Worker connectivity |
| POST | `/voice/debug` | STT→LLM chain (raw WAV/PCM body) |
| WS | `/ws/voice` | Real-time voice session |

## Modules

- **voice** (active) — AI Voice Lite with interruption handling
- **future modules** — add `modules/<name>/` + `api/routers/<name>.py`

## License

Private / portfolio project.
