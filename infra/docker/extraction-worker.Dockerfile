FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.6.2 /uv /uvx /bin/

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd -g 1001 appgroup && \
    useradd -u 1001 -g appgroup -m -s /bin/bash appuser

WORKDIR /app

COPY services/extraction-worker/ /app/

RUN uv venv /app/.venv \
    && . /app/.venv/bin/activate \
    && uv pip install --no-cache -e . \
    && chown -R appuser:appgroup /app

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

USER appuser

CMD ["python", "-m", "procurepilot_extraction_worker"]
