FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libsndfile1 \
    espeak-ng \
    && rm -rf /var/lib/apt/lists/*

COPY worker/requirements.txt .
# CPU PyTorch first (smaller image); Kokoro pulls weights from Hugging Face on startup.
RUN pip install --no-cache-dir --timeout 120 --retries 5 torch --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir --timeout 120 --retries 5 -r requirements.txt

COPY worker/ ./worker/

ENV KOKORO_LANG_CODE=a
ENV KOKORO_VOICE=af_sarah
ENV KOKORO_MAX_CHARS=150
ENV HF_HOME=/root/.cache/huggingface

EXPOSE 8000

CMD ["uvicorn", "worker.main:app", "--host", "0.0.0.0", "--port", "8000"]
