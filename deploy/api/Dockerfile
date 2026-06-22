FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml README.md ./
COPY api/ ./api/
COPY modules/ ./modules/

RUN pip install --no-cache-dir .

ENV API_HOST=0.0.0.0
ENV API_PORT=5000

EXPOSE 5000

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "5000"]
