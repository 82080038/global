FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ && \
    rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code and migration files
COPY src/ ./src/
COPY alembic/ ./alembic/
COPY alembic.ini .
COPY scripts/ ./scripts/
COPY .env.example .

# Run database migrations on startup
# Expose API port
EXPOSE 8000

# Health check — verify API is responding
HEALTHCHECK --interval=30s --timeout=5s --retries=3 --start-period=10s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')" || exit 1

# Run migrations then start API server
CMD ["sh", "-c", "alembic upgrade head && uvicorn src.trading_system.api.app:app --host 0.0.0.0 --port 8000"]
