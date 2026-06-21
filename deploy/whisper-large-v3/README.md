# Whisper Large v3 Turbo STT

Faster-Whisper worker for **[openai/whisper-large-v3-turbo](https://huggingface.co/openai/whisper-large-v3-turbo)** — higher accuracy than `deploy/whisper-stt/` (tiny), at the cost of latency and GPU memory.

## When to use

| Worker | Model | Port | Best for |
|--------|-------|------|----------|
| `whisper-stt/` | tiny | 5002 | Low latency, CPU OK |
| **`whisper-large-v3/`** | large-v3-turbo | **5004** | Clearer transcription, accents, noise |

Run **one STT worker at a time** (or pick port in root `.env`).

## Requirements

- NVIDIA GPU + [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html)
- Docker image uses `nvidia/cuda:12.6.1-cudnn-runtime` (includes libcublas for faster-whisper GPU)
- First start downloads ~1.5GB model weights into Docker volume
- If GPU libs fail, worker auto-falls back to **CPU** (much slower)

## Start

```bash
cd deploy/whisper-large-v3
cp .env.example .env
docker compose up -d --build
```

Point neomyth API to this worker in root `.env`:

```env
STT_BASE_URL=http://localhost:5004
```

## Health

```bash
curl http://localhost:5004/health
```

## Tuning

| Variable | Default | Notes |
|----------|---------|-------|
| `WHISPER_BEAM_SIZE` | 5 | Higher = clearer, slower. Use 1 for speed. |
| `WHISPER_COMPUTE_TYPE` | float16 | GPU. CPU not recommended for this model. |
| `WHISPER_LANGUAGE` | empty | Auto-detect. Set `en`, `id`, etc. to lock language. |
