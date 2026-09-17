FROM python:3.12-slim

# Install uv binary from official image
COPY --from=ghcr.io/astral-sh/uv:0.6.2 /uv /uvx /bin/

# Install runtime system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    libmagic1 \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user and group
RUN groupadd -g 1001 appgroup && \
    useradd -u 1001 -g appgroup -m -s /bin/bash appuser

# apps/api/pyproject.toml's [tool.uv.sources] resolves procurepilot-logging via the relative path
# ../../packages/py-logging (matching the real repo layout, needed so `uv run --project apps/api`
# also works from a plain checkout). This image mirrors that same two-levels-deep layout under
# /workspace so the identical relative path resolves here too.
WORKDIR /workspace/apps/api

# Create virtual environment and set ownership
RUN uv venv /workspace/apps/api/.venv && chown -R appuser:appgroup /workspace

ENV PATH="/workspace/apps/api/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/workspace/apps/api/src

COPY --chown=appuser:appgroup packages/py-logging/ /workspace/packages/py-logging/
COPY --chown=appuser:appgroup apps/api/ /workspace/apps/api/

USER appuser

RUN uv pip install --no-cache -e .

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/health || exit 1

CMD ["uvicorn", "procurepilot_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
