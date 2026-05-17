FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    DB_PATH=/data/boulderbat.db

# Install dependencies first for layer caching
COPY pyproject.toml ./
RUN uv sync --no-dev --no-install-project

# Copy application source
COPY app/ ./app/

VOLUME /data

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
