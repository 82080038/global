FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ && \
    rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY src/ ./src/
COPY main.py .
COPY .env.example .

# Expose API port
EXPOSE 8000

# Run API server
CMD ["uvicorn", "src.trading_system.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
