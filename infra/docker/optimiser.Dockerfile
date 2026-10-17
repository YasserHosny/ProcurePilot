FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.6.2 /uv /uvx /bin/

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd -g 1001 appgroup && \
    useradd -u 1001 -g appgroup -m -s /bin/bash appuser && \
    chmod o+rx /home/appuser

# The optimiser is an isolated deployable: it must not import procurepilot_api. It talks to
# Postgres through its own db.connect (prepare_threshold=None, required behind the Supabase
# transaction pooler) and to Redis/RQ only.
WORKDIR /workspace/services/optimiser

RUN uv venv /workspace/services/optimiser/.venv && chown -R appuser:appgroup /workspace

ENV PATH="/workspace/services/optimiser/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/workspace/services/optimiser/src

COPY --chown=appuser:appgroup services/optimiser/ /workspace/services/optimiser/

USER appuser

RUN uv pip install --no-cache -e .

CMD ["python", "-m", "procurepilot_optimiser_worker"]
