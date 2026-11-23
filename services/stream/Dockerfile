# Build context: the repo root.
FROM python:3.12-slim-bookworm AS build
RUN pip install --no-cache-dir uv==0.12.23
WORKDIR /app
ENV UV_PYTHON_DOWNLOADS=never UV_COMPILE_BYTECODE=1
COPY pyproject.toml uv.lock .python-version ./
# Every workspace member's pyproject.toml must exist for a frozen sync.
COPY collector/pyproject.toml collector/pyproject.toml
COPY services/api/pyproject.toml services/api/pyproject.toml
COPY services/carbon/pyproject.toml services/carbon/pyproject.toml
COPY services/ingest/pyproject.toml services/ingest/pyproject.toml
COPY services/orchestrator/pyproject.toml services/orchestrator/pyproject.toml
COPY libs libs
COPY services/stream services/stream
RUN uv sync --frozen --no-dev --no-editable --package airspace-stream

FROM python:3.12-slim-bookworm
RUN useradd --create-home --uid 10004 stream
COPY --from=build /app/.venv /app/.venv
ENV PATH=/app/.venv/bin:$PATH PYTHONUNBUFFERED=1
USER stream
# The worker touches the heartbeat after every check (at least once a minute).
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s CMD ["python", "-c", "import os, sys, time; sys.exit(time.time() - os.path.getmtime('/tmp/stream-heartbeat') > 180)"]
CMD ["python", "-m", "stream"]
