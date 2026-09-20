# syntax=docker/dockerfile:1
FROM python:3.11-slim AS base

# Build deps for psycopg and sentence-transformers wheels.
RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential curl \
 && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    # Models are cached in a named volume, not baked into the image: the
    # embedding model alone is over a gigabyte and changes independently.
    HF_HOME=/models \
    SENTENCE_TRANSFORMERS_HOME=/models

WORKDIR /app

# Dependencies first, so a source change does not re-resolve them.
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --upgrade pip && pip install ".[eval]"

COPY config ./config
COPY corpus ./corpus
COPY eval ./eval
COPY scripts ./scripts

# Non-root. The model cache has to be writable by it.
RUN useradd --create-home --uid 10001 appuser \
 && mkdir -p /models \
 && chown -R appuser:appuser /app /models
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
  CMD curl -fsS http://localhost:8000/health || exit 1

CMD ["uvicorn", "steel_assistant.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
