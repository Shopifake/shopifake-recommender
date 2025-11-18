# ===== Stage 1 — Build dependencies =====
FROM python:3.12-slim AS builder

# Environment setup
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=off \
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    PIP_DEFAULT_TIMEOUT=100

WORKDIR /app

# Install system deps for building Python packages
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc g++ libffi-dev && \
    rm -rf /var/lib/apt/lists/*

# Install Python dependencies inside a virtual environment
COPY requirements.txt .
RUN python -m venv /opt/venv && \
    . /opt/venv/bin/activate && \
    pip install --upgrade pip && \
    pip install -r requirements.txt


# ===== Stage 2 — Runtime =====
FROM python:3.12-slim AS runtime

# Labels for metadata
LABEL maintainer="FastAPI Template" \
      description="FastAPI production container" \
      version="1.0.0"

# Create non-root user for security
RUN useradd -m fastapiuser

# Copy venv from builder
COPY --from=builder /opt/venv /opt/venv

# Configure environment
# Sensitive variables (POSTGRES_*) should be passed at runtime, not baked into the image
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONOPTIMIZE=1 \
    ENVIRONMENT=production \
    POSTGRES_PORT=5432

# Install curl for healthcheck
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/* && \
    apt-get clean

WORKDIR /app

# Copy application code
COPY --chown=fastapiuser:fastapiuser ./src ./src

# Set permissions and switch to non-root user
USER fastapiuser

# Expose FastAPI port
EXPOSE 8000

# Health check using curl (production-ready)
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Launch app with Gunicorn + Uvicorn workers
CMD ["gunicorn", "src.main:app", \
     "--workers", "3", \
     "--worker-class", "uvicorn.workers.UvicornWorker", \
     "--bind", "0.0.0.0:8000", \
     "--keep-alive", "65", \
     "--timeout", "60", \
     "--access-logfile", "-", \
     "--error-logfile", "-"]
