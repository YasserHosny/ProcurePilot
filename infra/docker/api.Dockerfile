FROM python:3.12-slim

# Install uv binary from official image
COPY --from=ghcr.io/astral-sh/uv:0.6.2 /uv /uvx /bin/

# Install runtime system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user and group
RUN groupadd -g 1001 appgroup && \
    useradd -u 1001 -g appgroup -m -s /bin/bash appuser

WORKDIR /app

# Create virtual environment and set ownership
RUN uv venv /app/.venv && chown -R appuser:appgroup /app

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

# Copy shared logging package and install it first
COPY --chown=appuser:appgroup packages/py-logging/ /shared/py-logging/

# Copy API workspace files
COPY --chown=appuser:appgroup apps/api/ /app/

USER appuser

# Install shared package, then API in editable mode via uv
RUN uv pip install --no-cache /shared/py-logging && uv pip install --no-cache -e .

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/health || exit 1

CMD ["uvicorn", "procurepilot_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
