# syntax=docker/dockerfile:1

# ---- Stage 1: build the frontend ----
FROM node:22-alpine AS frontend
WORKDIR /src
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci || npm install
COPY frontend/ ./
RUN npm run build

# ---- Stage 2: runtime (FastAPI + built SPA, same origin) ----
FROM python:3.13-slim
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_LINK_MODE=copy \
    PIP_NO_CACHE_DIR=1

# uv (pinned) to drive the reproducible lockfile install.
COPY --from=ghcr.io/astral-sh/uv:0.5 /uv /uvx /bin/

# Keep the backend under /app/backend so the repo layout (and the config
# assumption that frontend/ lives next to backend/) holds in the image too.
WORKDIR /app
COPY backend/pyproject.toml backend/uv.lock ./backend/
COPY backend/app ./backend/app
COPY backend/alembic ./backend/alembic
COPY backend/alembic.ini ./backend/

WORKDIR /app/backend
RUN uv sync --frozen --no-dev

# Compiled SPA is served by the API (PILOTE_SERVE_FRONTEND=true).
COPY --from=frontend /src/dist /app/frontend/dist

ENV PILOTE_ENVIRONMENT=production \
    PILOTE_DEBUG=false \
    PILOTE_SERVE_FRONTEND=true \
    PILOTE_AUTO_MIGRATE=true

EXPOSE 10000

# Render sets PORT (default 10000). Migrations run during app startup via the
# lifespan hook; the SQLite->Postgres import is an operator step (DEPLOYMENT.md).
CMD ["sh", "-c", ".venv/bin/uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-10000}"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\", 10000)}/api/v1/health', timeout=4)"