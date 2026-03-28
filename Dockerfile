FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies first (cached layer)
COPY pyproject.toml .
RUN pip install --no-cache-dir .

# Copy application code and manifests
COPY pysandbox/ ./pysandbox/
COPY plugin_manifests/ ./plugin_manifests/

# Re-install in editable mode so pysandbox package is importable
RUN pip install --no-cache-dir -e .

EXPOSE 18080

HEALTHCHECK --interval=10s --timeout=3s --retries=3 \
    CMD curl -f http://localhost:18080/health || exit 1

CMD ["uvicorn", "pysandbox.main:app", "--host", "0.0.0.0", "--port", "18080"]
