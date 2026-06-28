# CLAUDE.md — Neomyth

Guide for Claude (Claude Code, Cowork, etc.) working in the **neomyth** monorepo.

> **Sync notice:** This file mirrors [`AGENTS.md`](AGENTS.md) (used by Cursor and other agents). Whenever one file is updated, update the other to keep Cursor and Claude in sync.

## Project overview

Neomyth is a multi-module monorepo for AI applications. The architecture separates four layers:

1. **`web/`** — Astro frontend (SSG, shadcn/ui, SEO)
2. **`api/`** — FastAPI gateway (transport: HTTP JSON, WebSocket)
3. **`modules/`** — Core AI logic (orchestration, graph, HTTP clients to workers)
4. **`deploy/`** — Docker workers (model loading, inference, GPU)

**Active module:** `voice` (AI Voice Lite — STT → LLM → TTS, WebSocket full-duplex).

**Upcoming modules:** add as `modules/<name>/` + `api/routers/<name>.py` + optional `deploy/<worker>/`.

## Directory structure

```text
neomyth/
├── AGENTS.md                   # Cursor / general agent guide — mirrors this file
├── CLAUDE.md                   # this file — mirrors AGENTS.md
├── pyproject.toml              # single source of Python dependencies (API + modules)
├── .python-version             # Python 3.12
├── .env.example                # runtime env template (URLs, ports)
├── README.md
│
├── web/                        # Astro frontend — SSG, shadcn/ui
│   ├── src/layouts/
│   │   ├── BaseLayout.astro
│   │   └── ToolPageLayout.astro  # all tool pages (/voice, future tools)
│   ├── src/pages/              # landing (/), tools (/voice, …)
│   ├── src/components/
│   │   ├── ToolControlPanel.tsx
│   │   ├── ChatMessages.tsx
│   │   └── ui/                 # shadcn primitives
│   └── public/                 # robots.txt, llms.txt
│
├── api/                        # FastAPI gateway — transport only
│   ├── main.py
│   ├── config.py               # pydantic-settings from .env
│   └── routers/
│       └── voice.py
│
├── modules/                    # core AI — no FastAPI, no model loading
│   ├── shared/                 # cross-module utils & tunable constants
│   │   ├── constants.py
│   │   ├── types.py
│   │   └── utils/
│   │       ├── audio.py
│   │       ├── text.py
│   │       └── http.py
│   └── voice/                  # MODULE 1
│       ├── protocol.py
│       ├── graph.py
│       ├── pipeline.py
│       └── clients/
│           ├── stt.py
│           ├── llm.py
│           └── tts.py
│
├── deploy/                     # Docker workers & orchestration
│   ├── docker-compose.yml
│   ├── vllm-llm/               # LLM worker (Qwen3.5-0.8B via vLLM) :5001
│   ├── whisper-stt/            # Faster-Whisper worker :5002
│   ├── kokoro-tts/             # Kokoro-82M worker :5003
│   ├── tei-embedding/          # future RAG worker
│   └── api/                    # optional Docker image for api layer
│
└── docs/
    ├── ui-layout-guide.md      # tool page UI standard (required for new tools)
    └── neomyth-voice/
        └── architecture.md
```

## Frontend UI (tool pages)

All tool routes (`/voice`, future `/parse`, `/spec`, …) **must** use [`ToolPageLayout.astro`](web/src/layouts/ToolPageLayout.astro). See **[docs/ui-layout-guide.md](docs/ui-layout-guide.md)** for:

- Page shell (back link, h1, description)
- `ToolControlPanel` + work area stack
- `ChatMessages` for conversational UIs
- Page-level scroll and hydration rules
- Checklist for adding a new tool

Landing (`/`) keeps its own marketing layout — do not use `ToolPageLayout` there.

## Layer boundaries (strict)

| Layer | Responsibility | Allowed imports | Forbidden |
|-------|----------------|-----------------|-----------|
| `api/` | Routing, WS I/O, CORS, runtime config | `modules.*`, FastAPI stack | Business AI logic, ML libs, HTML/UI |
| `modules/shared/` | Shared constants, pure utils, shared types | stdlib, generic libs (no module-specific) | Import from `modules/voice` or other feature modules |
| `modules/<name>/` | Orchestration, graph, protocol, worker HTTP clients | `modules.shared`, `httpx`, `openai` | FastAPI routes, direct model loading |
| `deploy/<worker>/` | Thin FastAPI inference worker, Dockerfile | ML libs for that worker only | Orchestration graph, imports from `modules/` |

**Dependency direction:** `api` → `modules/<name>` → `modules/shared`. Never reverse.

## Config vs constants

Do not mix runtime env with code-level tunables.

| Location | Examples | Source |
|----------|----------|--------|
| `api/config.py` | `VLLM_BASE_URL`, `STT_BASE_URL`, `API_PORT` | `.env` |
| `modules/shared/constants.py` | `AUDIO_SAMPLE_RATE`, `MAX_HISTORY_TURNS`, `SENTENCE_CHUNK_MIN_CHARS` | Python constants |

Worker-specific env lives in `deploy/<worker>/.env.example` (e.g. `WHISPER_MODEL`, `KOKORO_VOICE`).

## Dependencies

- **Root `pyproject.toml`** — API + modules only: `fastapi`, `uvicorn`, `pydantic-settings`, `openai`, `httpx`, `langgraph`.
- **No ML libs in root** — `faster-whisper`, `kokoro-onnx`, `numpy` belong in `deploy/<worker>/worker/requirements.txt`.
- Do not add per-module `pyproject.toml`; keep dependencies centralized at root.

## Voice module pipeline

```text
Browser (Astro web/)
  → WebSocket → api/routers/voice.py
  → modules/voice/pipeline.py
      → modules/voice/clients/stt.py  → deploy/whisper-stt
      → modules/voice/clients/llm.py  → deploy/vllm-llm (OpenAI-compatible)
      → modules/voice/clients/tts.py  → deploy/kokoro-tts
      → modules/voice/graph.py        (LangGraph STT→LLM→TTS, MemorySaver)
      → modules/shared/utils/*        (chunking, audio helpers)
```

**LLM defaults** (align with `deploy/vllm-llm/.env.example`):

- Model ID: `Qwen/Qwen3.5-0.8B`
- Served name: `qwen-3.5`
- Base URL: `http://localhost:5001/v1`

## Adding a new module

1. Create `modules/<name>/` with orchestration logic (no FastAPI).
2. Add `api/routers/<name>.py` and register in `api/main.py`.
3. Reuse `modules/shared/` for generic helpers; do not duplicate.
4. If inference is heavy, add `deploy/<worker>/` thin HTTP worker — do not load models in `api/` or `modules/`.
5. Extend root `.env.example` and `api/config.py` for new worker URLs.
6. Document in `docs/<name>/` if non-trivial.

## Language

All text written into the codebase must be in **English**. This includes:

- Code comments, docstrings, and type-hint descriptions
- Documentation (`README.md`, `docs/`, `AGENTS.md`, `CLAUDE.md`)
- Config and deploy comments (`.env.example`, `docker-compose.yml`, worker env templates)
- User-facing copy (WebSocket protocol fields, `web/` UI strings)
- Variable names, function names, and log messages (already English by convention — keep it consistent)

Do not add Indonesian or other non-English prose in source files unless it is intentional product copy for a localized feature (e.g. a language-specific TTS prompt). Even then, keep code structure, comments, and docs in English.

## Coding conventions

- **Minimize scope** — smallest correct change; match existing style.
- **Async** — use `async/await` in API and modules; workers can be sync inside inference if simpler.
- **Cancellation** — voice pipeline must support interrupt: cancel asyncio tasks, use generation IDs to drop stale chunks.
- **Imports** — `from modules.voice.pipeline import VoicePipeline` (package root is repo root; `PYTHONPATH=.` or hatchling config).
- **Comments** — only for non-obvious business or concurrency logic.
- **Tests** — add only when requested or when covering real behavior.

## Dev workflow

```bash
# Workers
cd deploy/vllm-llm && docker compose up -d
cd deploy/whisper-stt && docker compose up -d
cd deploy/kokoro-tts && docker compose up -d

# API (local)
cp .env.example .env
uv run uvicorn api.main:app --host 0.0.0.0 --port 5000 --reload

# Frontend
cd web && npm install && npm run dev

# Or full stack
cd deploy && docker compose --profile full up -d
```

Landing: `http://localhost:4321` · Neo-Voice: `http://localhost:4321/voice`

On Windows Docker, API may need `host.docker.internal` to reach workers from containers.

## Common mistakes (avoid)

- Putting orchestration or graph logic in `api/routers/`.
- Importing `faster-whisper` or `kokoro` in `modules/` or `api/`.
- Adding feature-specific code to `modules/shared/` (keep it generic).
- Creating duplicate `pyproject.toml` under `modules/`.
- Hardcoding worker URLs instead of `api/config.py`.
- Loading ML models in the API process.

## Agent task routing

| Task | Work in |
|------|---------|
| Landing, SEO, shadcn UI | `web/` |
| **New tool page UI** | `web/src/layouts/ToolPageLayout.astro`, `docs/ui-layout-guide.md` |
| New HTTP/WebSocket endpoint | `api/routers/`, `api/main.py` |
| Pipeline / graph / interrupt logic | `modules/voice/` |
| Shared chunking, audio, HTTP helpers | `modules/shared/` |
| STT/TTS/LLM inference or GPU | `deploy/<worker>/` |
| Docker orchestration | `deploy/docker-compose.yml` |
| Env vars & ports | `.env.example`, `api/config.py`, `deploy/*/.env.example` |

## Portfolio goals (voice module)

- End-to-end voice latency target: **&lt;1.2s** (speech end → first TTS audio).
- Full-duplex WebSocket with **smart interruption** when user speaks during AI playback.
- Structured conversation context via LangGraph in `modules/voice/graph.py` (in-memory checkpoint per WebSocket session).
