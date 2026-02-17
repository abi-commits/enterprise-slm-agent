# Knowledge Service Dockerfile (Search + Ingestion)
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast package management
RUN pip install uv

# Copy dependency files
COPY pyproject.toml ./

# Install dependencies using uv
RUN uv pip install --system -r pyproject.toml

# Copy core and service code
COPY core/ ./core/
COPY services/__init__.py ./services/__init__.py
COPY services/knowledge/ ./services/knowledge/

# Set Python path
ENV PYTHONPATH=/app:$PYTHONPATH

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run the service
CMD ["uvicorn", "services.knowledge.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
