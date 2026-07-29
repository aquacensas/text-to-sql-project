# Dockerfile
# Base image — Python 3.11 slim for smaller image size
FROM python:3.11-slim

# Set working directory inside container
WORKDIR /app

# Install system dependencies needed for psycopg2
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first — Docker caches this layer
# so we only reinstall packages when requirements.txt changes
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ ./app/
COPY frontend/ ./frontend/
COPY evals/ ./evals/

# Set Python path so imports work correctly
ENV PYTHONPATH=/app/app

# Default command — starts FastAPI
# Can be overridden in docker-compose.yml for Streamlit
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]