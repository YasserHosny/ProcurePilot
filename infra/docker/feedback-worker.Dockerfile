FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.6.2 /uv /uvx /bin/

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    libmagic1 \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd -g 1001 appgroup && \
    useradd -u 1001 -g appgroup -m -s /bin/bash appuser

# Same layout as email-ingestion-worker.Dockerfile: apps/api/pyproject.toml resolves
# procurepilot-logging via ../../packages/py-logging, so the image mirrors the repo layout under
# /workspace for that relative path to resolve.
WORKDIR /workspace/apps/api

RUN uv venv /workspace/apps/api/.venv && chown -R appuser:appgroup /workspace

ENV PATH="/workspace/apps/api/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/workspace/apps/api/src

COPY --chown=appuser:appgroup packages/py-logging/ /workspace/packages/py-logging/
# The operator digest is rendered from packages/i18n (emails.feedbackDigest.*).
COPY --chown=appuser:appgroup packages/i18n/ /workspace/packages/i18n/
COPY --chown=appuser:appgroup apps/api/ /workspace/apps/api/

USER appuser

RUN uv pip install --no-cache -e .

# Long-running loop, not a request-serving process -- no EXPOSE/HEALTHCHECK. Every 900 s it runs
# the spec 025 jobs: operator daily digest, 12-month retention purge, orphan-storage sweep (see
# feedback_worker.py's tick()). Run exactly one instance: the digest has no cross-process lock.
CMD ["python", "-m", "procurepilot_api.workers.feedback_worker", "--interval", "900"]
