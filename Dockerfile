FROM python:3.11-slim

WORKDIR /app

# Install system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Create workspace directory for file tools
RUN mkdir -p /app/workspace /app/chroma_db

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# Default command — override in docker-compose / render.yaml as needed.
# Shell form so ${PORT} (injected by Render) is expanded; falls back to 8000 locally.
CMD uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8000}
