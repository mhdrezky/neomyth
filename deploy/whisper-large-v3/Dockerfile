# CUDA runtime so faster-whisper/ctranslate2 can use GPU (libcublas, etc.)
FROM nvidia/cuda:12.6.1-cudnn-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-venv \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/* \
    && ln -sf /usr/bin/python3 /usr/bin/python

COPY worker/requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

COPY worker/ ./worker/

ENV WHISPER_MODEL=large-v3-turbo
ENV WHISPER_DEVICE=cuda
ENV WHISPER_COMPUTE_TYPE=float16
ENV WHISPER_BEAM_SIZE=5

EXPOSE 8000

CMD ["python3", "-m", "uvicorn", "worker.main:app", "--host", "0.0.0.0", "--port", "8000"]
