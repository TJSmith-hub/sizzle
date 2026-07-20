# syntax=docker/dockerfile:1
FROM python:3.12-slim

# Bring in the uv binary from its official image.
COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /uvx /bin/

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DATABASE_PATH=/data/recipes.db \
    # Use the image's own Python, compile bytecode on install, copy (not link)
    # into the venv since the cache and target may be on different mounts.
    UV_PYTHON_DOWNLOADS=never \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

# lxml (a recipe-scrapers dependency) ships manylinux wheels, so no compiler is
# normally needed. If you hit a build error on an unusual architecture, uncomment:
# RUN apt-get update && apt-get install -y --no-install-recommends \
#     gcc libxml2-dev libxslt1-dev && rm -rf /var/lib/apt/lists/*

# Install locked runtime dependencies first (no dev deps) for better layer caching.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY app ./app

# The SQLite database lives here; mount it as a volume (see docker-compose.yml).
RUN mkdir -p /data
VOLUME ["/data"]

EXPOSE 8000

CMD ["uv", "run", "--frozen", "--no-dev", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
