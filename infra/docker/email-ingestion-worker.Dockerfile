FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.6.2 /uv /uvx /bin/

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    libmagic1 \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd -g 1001 appgroup && \
    useradd -u 1001 -g appgroup -m -s /bin/bash appuser

# apps/api/pyproject.toml's [tool.uv.sources] resolves procurepilot-logging via the relative path
# ../../packages/py-logging (matching the real repo layout, needed so `uv run --project apps/api`
# also works from a plain checkout). This image mirrors that same two-levels-deep layout under
# /workspace so the identical relative path resolves here too -- same convention as
# api.Dockerfile and extraction-worker.Dockerfile.
WORKDIR /workspace/apps/api

RUN uv venv /workspace/apps/api/.venv && chown -R appuser:appgroup /workspace

ENV PATH="/workspace/apps/api/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/workspace/apps/api/src

COPY --chown=appuser:appgroup packages/py-logging/ /workspace/packages/py-logging/
COPY --chown=appuser:appgroup apps/api/ /workspace/apps/api/

USER appuser

RUN uv pip install --no-cache -e .

# Long-running poll loop, not a request-serving process -- no EXPOSE/HEALTHCHECK. Polls
# ingestion_jobs for job_type='email_ingest' every 15s; see email_ingestion_worker.py's
# run_loop()/tick() for the claim-and-process cycle this replaces the never-deployed manual
# invocation with.
CMD ["python", "-m", "procurepilot_api.workers.email_ingestion_worker", "--interval-seconds", "15"]
