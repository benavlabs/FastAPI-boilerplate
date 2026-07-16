# ===================== Requirements Export Stage =====================
# Export requirements from uv.lock for reproducible, secure builds
FROM python:3.11-slim AS requirements-stage

WORKDIR /tmp

# Use official uv image with pinned version for reproducibility
COPY --from=ghcr.io/astral-sh/uv:0.9.9 /uv /usr/local/bin/uv

# Copy the workspace manifests + lock for deterministic export. The build
# context must be the WORKSPACE ROOT: uv.lock lives there (not in backend/),
# and resolving the workspace needs every member manifest.
COPY pyproject.toml uv.lock ./
COPY backend/pyproject.toml backend/pyproject.toml
COPY cli/pyproject.toml cli/pyproject.toml

# Export from lock file (not re-resolving dependencies!)
# Filter out the local project line ("./backend") and keep only external deps
RUN uv export --package fastapi-boilerplate --no-dev --no-editable -o /tmp/req-full.txt && \
    grep -vE "^\.(/backend)?$" /tmp/req-full.txt > requirements-prod.txt

# Export dev requirements (the backend's `dev` extra) from lock file
RUN uv export --package fastapi-boilerplate --extra dev --no-editable -o /tmp/req-dev-full.txt && \
    grep -vE "^\.(/backend)?$" /tmp/req-dev-full.txt > requirements-dev.txt

# ===================== Production Base Stage =====================
FROM python:3.11-slim AS base

WORKDIR /app

# Install uv for fast, secure package installation  
COPY --from=ghcr.io/astral-sh/uv:0.9.9 /uv /usr/local/bin/uv

# Install system dependencies needed for Python packages
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Copy and install production requirements with uv (fast + hash verification)
COPY --from=requirements-stage /tmp/requirements-prod.txt .
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --system -r requirements-prod.txt && \
    rm requirements-prod.txt

# Copy source code
COPY backend/src ./src

# Set Python path
ENV PYTHONPATH=/app/src

# ===================== Development Stage =====================
FROM base AS dev

WORKDIR /app/src

# Copy and install dev requirements with uv (fast + hash verification)
COPY --from=requirements-stage /tmp/requirements-dev.txt .
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --system -r requirements-dev.txt && \
    rm requirements-dev.txt

# Copy test files for development
COPY backend/tests ./tests

# Create non-root user for security (same as production)
RUN groupadd -r appuser && useradd -r -m -g appuser appuser
RUN chown -R appuser:appuser /app
USER appuser

# Add quality-of-life configs for development
ENV PYTHONUNBUFFERED=1

# Development command with FastAPI CLI auto-reload
CMD ["fastapi", "dev", "interfaces/main.py", "--host", "0.0.0.0", "--port", "8000"]

# ===================== Migration Stage =====================
FROM base AS migrate

# Optional build arg for CI/CD pipelines
ARG DATABASE_URL=""

# Copy migration files
COPY backend/migrations ./migrations
COPY backend/alembic.ini .

# Create non-root user for security
RUN groupadd -r appuser && useradd -r -m -g appuser appuser
RUN chown -R appuser:appuser /app
USER appuser

# Set build-time DATABASE_URL as environment variable if provided
ENV DATABASE_URL=${DATABASE_URL}

# Default command runs migrations
CMD ["alembic", "upgrade", "head"]

# ===================== Production Stage =====================
FROM base AS prod

WORKDIR /app/src

# Create non-root user for security
RUN groupadd -r appuser && useradd -r -m -g appuser appuser
RUN chown -R appuser:appuser /app
USER appuser

# Production command with FastAPI CLI and configurable workers
ENV WORKERS=1
CMD ["sh", "-c", "fastapi run interfaces/main.py --host 0.0.0.0 --port 8000 --workers $WORKERS"] 