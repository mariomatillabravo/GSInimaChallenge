# syntax=docker/dockerfile:1

# ---- Build stage: install the locked runtime dependencies into a virtual environment --------
FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.12.17 /uv /usr/local/bin/uv

# Compile bytecode at build time for faster startup; use the image's Python, never a download.
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app
# Dependencies change less often than code: copying them first keeps this layer cached.
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --locked --no-dev --no-install-project

# ---- Runtime stage: Python, the virtual environment and the application, nothing else -------
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app
# /app belongs to root, so the cache folder is created here and handed to the app user. A named
# volume mounted on it starts with this ownership, which lets the app create the SQLite files.
RUN useradd --create-home --uid 10001 app \
    && mkdir /app/data \
    && chown app:app /app/data

COPY --from=builder /app/.venv /app/.venv
COPY app ./app
COPY sample_data/demo ./sample_data/demo

# Never run as root inside the container.
USER app

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)"]

CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
