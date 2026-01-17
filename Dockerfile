FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY pyproject.toml ./
RUN pip install --no-cache-dir -e .

# Copy application code
COPY src/ ./src/
COPY config/ ./config/

# Create data directory
RUN mkdir -p /app/data

# Run as non-root user
RUN useradd --create-home appuser && chown -R appuser:appuser /app
USER appuser

# Default command
CMD ["python", "-m", "market_maker", "--mode", "paper"]
