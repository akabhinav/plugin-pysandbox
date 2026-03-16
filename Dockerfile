FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY pyproject.toml .
RUN pip install --no-cache-dir -e ".[dev]" 2>/dev/null || pip install --no-cache-dir .

# Copy application
COPY . .

# Install the package
RUN pip install --no-cache-dir -e .

EXPOSE 8080

CMD ["uvicorn", "pysandbox.main:app", "--host", "0.0.0.0", "--port", "8080"]
