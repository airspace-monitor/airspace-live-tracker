# Build context: the repo root.
FROM python:3.12-slim-bookworm AS build
RUN pip install --no-cache-dir uv==0.12.23
WORKDIR /app
ENV UV_PYTHON_DOWNLOADS=never UV_COMPILE_BYTECODE=1
COPY pyproject.toml uv.lock .python-version ./
# Every workspace member's pyproject.toml must exist for a frozen sync.
COPY collector/pyproject.toml collector/pyproject.toml
COPY services/api/pyproject.toml services/api/pyproject.toml
COPY services/ingest/pyproject.toml services/ingest/pyproject.toml
COPY services/orchestrator/pyproject.toml services/orchestrator/pyproject.toml
COPY services/stream/pyproject.toml services/stream/pyproject.toml
COPY libs libs
COPY services/carbon services/carbon
RUN uv sync --frozen --no-dev --no-editable --package airspace-carbon

FROM python:3.12-slim-bookworm
RUN useradd --create-home --uid 10005 carbon
COPY --from=build /app/.venv /app/.venv
ENV PATH=/app/.venv/bin:$PATH PYTHONUNBUFFERED=1
USER carbon
EXPOSE 8002
HEALTHCHECK --interval=15s --timeout=5s --start-period=10s CMD ["python", "-c", "import urllib.request as u; u.urlopen('http://127.0.0.1:8002/healthz', timeout=4)"]
CMD ["uvicorn", "--factory", "carbon.app:create_app", "--host", "0.0.0.0", "--port", "8002", "--no-access-log"]
