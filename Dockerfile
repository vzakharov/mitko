FROM python:3.11-slim AS base

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy dependency files first (layer caching)
COPY pyproject.toml uv.lock ./

# Install dependencies only (no dev deps, skip project itself)
RUN uv sync --frozen --no-dev --no-install-project

# Copy source
COPY src/ src/
COPY alembic/ alembic/
COPY alembic.ini .

# Install project package (deps already cached above)
RUN uv sync --frozen --no-dev

# Run migrations + start server
# Railway injects $PORT automatically
CMD uv run alembic upgrade head && \
    uv run uvicorn src.mitko.main:app --host 0.0.0.0 --port ${PORT:-8000}
