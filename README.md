# Neomyth

Multi-module AI monorepo with an Astro frontend, FastAPI gateway, and Docker inference workers.

## Architecture

```text
Browser  →  web/ (Astro)     landing + Neo-Voice UI
         →  api/ (FastAPI)   WebSocket + JSON API
         →  modules/voice/   orchestration
                ↓
         deploy/vllm-llm · whisper-stt · kokoro-tts (workers)
```

| Layer | Path | Role |
|-------|------|------|
| Frontend | `web/` | Astro SSG, shadcn/ui, SEO |
| Gateway | `api/` | HTTP JSON, WebSocket |
| Core AI | `modules/voice/` | Pipeline, graph, worker clients |
| Shared | `modules/shared/` | Constants, utils |
| Workers | `deploy/*/` | STT, LLM, TTS inference |

See [AGENTS.md](AGENTS.md), [docs/ui-layout-guide.md](docs/ui-layout-guide.md), and [docs/neomyth-voice/architecture.md](docs/neomyth-voice/architecture.md).

## Prerequisites

- Python 3.12+ and [uv](https://docs.astral.sh/uv/)
- Node.js 20+ and npm
- Docker with NVIDIA GPU support (recommended)
- Microphone + speakers for Neo-Voice

## Quick start

### 1. Workers

```bash
cd deploy/vllm-llm && docker compose up -d
cd ../whisper-large-v3 && docker compose up -d
cd ../kokoro-tts && docker compose up -d
```

Or: `cd deploy && docker compose --profile workers up -d`

### 2. API

```bash
cp .env.example .env
uv sync
uv run uvicorn api.main:app --host 0.0.0.0 --port 5000 --reload
```

### 3. Frontend

```bash
cd web
cp .env.example .env
npm install
npm run dev
```

- Landing: **http://localhost:4321**
- Neo-Voice: **http://localhost:4321/voice** (WebSocket → API on port 5000)

## Environment

| Variable | Default | Description |
|----------|---------|-------------|
| `API_PORT` | `5000` | FastAPI port |
| `PUBLIC_API_BASE_URL` | `http://localhost:5000` | API URL for web (in `web/.env`) |
| `PUBLIC_SITE_URL` | `http://localhost:4321` | Site URL for SEO/sitemap |
| `VLLM_BASE_URL` | `http://localhost:5001/v1` | vLLM OpenAI API |
| `STT_BASE_URL` | `http://localhost:5004` | Whisper worker |
| `TTS_BASE_URL` | `http://localhost:5003` | Kokoro worker |

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | API info JSON |
| GET | `/health` | API health |
| GET | `/voice/health` | Worker connectivity |
| POST | `/voice/debug` | STT→LLM chain (raw audio body) |
| WS | `/ws/voice` | Real-time voice session |

## Web — shadcn/ui

```bash
cd web
npx shadcn@latest add <component>
```

Static pages use shadcn without `client:*`. Interactive islands use `client:load`.

New tool pages must follow [docs/ui-layout-guide.md](docs/ui-layout-guide.md) (`ToolPageLayout`, `ToolControlPanel`).

## Modules

- **Neo-Voice** (active) — real-time voice assistant
- **Neo-Parse**, **Neo-Spec** — coming soon (landing cards only)

## License

Private / portfolio project.
