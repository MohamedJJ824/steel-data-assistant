# syntax=docker/dockerfile:1
FROM python:3.11-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends curl \
 && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# The UI talks to the API over HTTP only, so it needs neither the database
# driver nor the embedding models.
RUN pip install --upgrade pip && pip install "streamlit>=1.38" "httpx>=0.27" "pandas>=2.2"

COPY ui ./ui

RUN useradd --create-home --uid 10002 uiuser && chown -R uiuser:uiuser /app
USER uiuser

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
  CMD curl -fsS http://localhost:8501/_stcore/health || exit 1

CMD ["streamlit", "run", "ui/app.py", "--server.port=8501", "--server.address=0.0.0.0", "--server.headless=true"]
