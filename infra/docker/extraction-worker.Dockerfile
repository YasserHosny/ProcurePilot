FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.6.2 /uv /uvx /bin/

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd -g 1001 appgroup && \
    useradd -u 1001 -g appgroup -m -s /bin/bash appuser && \
    chmod o+rx /home/appuser

# services/extraction-worker/pyproject.toml's [tool.uv.sources] resolves procurepilot-logging via
# the relative path ../../packages/py-logging (matching the real repo layout, needed so
# `uv run --project services/extraction-worker` also works from a plain checkout). This image
# mirrors that same two-levels-deep layout under /workspace so the identical relative path
# resolves here too.
WORKDIR /workspace/services/extraction-worker

RUN uv venv /workspace/services/extraction-worker/.venv && chown -R appuser:appgroup /workspace

ENV PATH="/workspace/services/extraction-worker/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/workspace/services/extraction-worker/src

COPY --chown=appuser:appgroup packages/py-logging/ /workspace/packages/py-logging/
COPY --chown=appuser:appgroup services/extraction-worker/ /workspace/services/extraction-worker/

USER appuser

RUN uv pip install --no-cache -e .

CMD ["python", "-m", "procurepilot_extraction_worker"]
