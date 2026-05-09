# ISA-CAD / ArchTwin FastAPI — deploy on Render, Railway, Fly.io, etc.
# Health check: GET /api/health

FROM python:3.11-slim-bookworm

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY isa_cad ./isa_cad

RUN pip install --upgrade pip setuptools wheel \
    && pip install --no-cache-dir .

EXPOSE 8000

# Render / Railway / Fly set PORT; default 8000 for local docker run
CMD ["sh", "-c", "exec uvicorn isa_cad.api.server:app --host 0.0.0.0 --port ${PORT:-8000}"]
