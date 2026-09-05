FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.6.2 /uv /uvx /bin/

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd -g 1001 appgroup && \
    useradd -u 1001 -g appgroup -m -s /bin/bash appuser && \
    chmod o+rx /home/appuser

WORKDIR /app

RUN uv venv /app/.venv && chown -R appuser:appgroup /app

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

COPY --chown=appuser:appgroup packages/py-logging/ /shared/py-logging/
COPY --chown=appuser:appgroup services/extraction-worker/ /app/

USER appuser

RUN uv pip install --no-cache /shared/py-logging \
    && uv pip install --no-cache -e .

CMD ["python", "-m", "procurepilot_extraction_worker"]
