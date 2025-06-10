# Installation Guide

This guide covers different ways to install and set up the FastAPI Boilerplate depending on your needs and environment.

## System Requirements

Before you begin, ensure your system meets these requirements:

- **Python**: 3.11 or higher
- **Operating System**: Linux, macOS, or Windows (with WSL2 recommended)
- **Memory**: Minimum 4GB RAM (8GB recommended)
- **Disk Space**: At least 2GB free space

## Method 1: Docker Compose (Recommended)

Docker Compose is the easiest way to get started. It handles all dependencies and services automatically.

### Prerequisites

Install these tools on your system:

- [Docker](https://docs.docker.com/get-docker/) (version 20.10+)
- [Docker Compose](https://docs.docker.com/compose/install/) (version 1.29+)

### Installation Steps

1. **Get the template**:
   ```bash
   git clone https://github.com/benavlabs/fastapi-boilerplate
   cd fastapi-boilerplate
   ```

2. **Set up environment**:
   ```bash
   cp src/.env.example src/.env
   # Edit src/.env with your configuration
   ```

3. **Start services**:
   ```bash
   docker compose up -d
   ```

4. **Verify installation**:
   ```bash
   curl http://localhost:8000/docs
   ```

### What Gets Installed

Docker Compose sets up these services:

- **Web server** (FastAPI + Uvicorn) on port 8000
- **PostgreSQL** database on port 5432 (internal)
- **Redis** server on port 6379 (internal)
- **ARQ Worker** for background tasks
- **NGINX** (optional, for production)

## Method 2: Manual Installation

For more control or development purposes, you can install everything manually.

### Prerequisites

1. **Install Python 3.11+**:
   ```bash
   # On Ubuntu/Debian
   sudo apt update
   sudo apt install python3.11 python3.11-pip
   
   # On macOS (with Homebrew)
   brew install python@3.11
   
   # On Windows
   # Download from python.org
   ```

2. **Install uv** (Python package manager):
   ```bash
   pip install uv
   ```

3. **Install PostgreSQL**:
   ```bash
   # On Ubuntu/Debian
   sudo apt install postgresql postgresql-contrib
   
   # On macOS
   brew install postgresql
   
   # On Windows
   # Download from postgresql.org
   ```

4. **Install Redis**:
   ```bash
   # On Ubuntu/Debian
   sudo apt install redis-server
   
   # On macOS
   brew install redis
   
   # On Windows
   # Download from redis.io
   ```

### Installation Steps

1. **Clone the repository**:
   ```bash
   git clone https://github.com/benavlabs/fastapi-boilerplate
   cd fastapi-boilerplate
   ```

2. **Install Python dependencies**:
   ```bash
   uv sync
   ```

3. **Set up environment variables**:
   ```bash
   cp src/.env.example src/.env
   # Edit src/.env with your local database/Redis settings
   ```

4. **Set up PostgreSQL**:
   ```bash
   # Create database and user
   sudo -u postgres psql
   CREATE DATABASE myapp;
   CREATE USER myuser WITH PASSWORD 'mypassword';
   GRANT ALL PRIVILEGES ON DATABASE myapp TO myuser;
   \q
   ```

5. **Run database migrations**:
   ```bash
   cd src
   uv run alembic upgrade head
   ```

6. **Create admin user**:
   ```bash
   uv run python -m src.scripts.create_first_superuser
   ```

7. **Start the application**:
   ```bash
   uv run uvicorn src.app.main:app --reload --host 0.0.0.0 --port 8000
   ```

8. **Start the worker** (in another terminal):
   ```bash
   uv run arq src.app.core.worker.settings.WorkerSettings
   ```

## Method 3: Development Setup

For contributors and advanced users who want to modify the boilerplate.

### Additional Prerequisites

- **Git** for version control
- **Pre-commit** for code quality

### Installation Steps

1. **Fork and clone**:
   ```bash
   # Fork the repository on GitHub first
   git clone https://github.com/yourusername/fastapi-boilerplate
   cd fastapi-boilerplate
   ```

2. **Install development dependencies**:
   ```bash
   uv sync --group dev
   ```

3. **Set up pre-commit hooks**:
   ```bash
   uv run pre-commit install
   ```

4. **Set up development environment**:
   ```bash
   cp src/.env.example src/.env
   # Configure for development
   ```

5. **Run tests to verify setup**:
   ```bash
   uv run pytest
   ```

## Docker Services Breakdown

Understanding what each Docker service does:

### Web Service
```yaml
web:
  build: .
  ports:
    - "8000:8000"
  depends_on:
    - db
    - redis
```
- Runs the FastAPI application
- Handles HTTP requests
- Auto-reloads on code changes (development)

### Database Service
```yaml
db:
  image: postgres:13
  environment:
    POSTGRES_DB: myapp
    POSTGRES_USER: postgres
    POSTGRES_PASSWORD: changethis
```
- PostgreSQL database server
- Persistent data storage
- Automatic initialization

### Redis Service
```yaml
redis:
  image: redis:alpine
  command: redis-server --appendonly yes
```
- In-memory data store
- Used for caching and job queues
- Persistent storage with AOF

### Worker Service
```yaml
worker:
  build: .
  command: arq src.app.core.worker.settings.WorkerSettings
  depends_on:
    - redis
```
- Background task processor
- Handles async jobs
- Scales independently

## Configuration

### Environment Variables

The application uses environment variables for configuration. Key variables:

```env
# Database
POSTGRES_USER=postgres
POSTGRES_PASSWORD=changethis
POSTGRES_SERVER=localhost  # or "db" for Docker
POSTGRES_PORT=5432
POSTGRES_DB=myapp

# Redis
REDIS_CACHE_HOST=localhost  # or "redis" for Docker
REDIS_CACHE_PORT=6379

# Security
SECRET_KEY=your-secret-key-here
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
```

### Database Connection

For manual installation, update your database settings:

```env
# Local PostgreSQL
POSTGRES_SERVER=localhost
POSTGRES_PORT=5432

# Docker PostgreSQL
POSTGRES_SERVER=db
POSTGRES_PORT=5432
```

## Verification

After installation, verify everything works:

1. **API Documentation**: http://localhost:8000/docs
2. **Health Check**: http://localhost:8000/api/v1/health
3. **Database Connection**: Check logs for successful connection
4. **Redis Connection**: Test caching functionality
5. **Background Tasks**: Submit a test job

## Troubleshooting

### Common Issues

**Port Already in Use**:
```bash
# Check what's using port 8000
lsof -i :8000

# Kill the process
kill -9 <PID>
```

**Database Connection Error**:
```bash
# Check PostgreSQL status
sudo systemctl status postgresql

# Restart PostgreSQL
sudo systemctl restart postgresql
```

**Redis Connection Error**:
```bash
# Check Redis status
redis-cli ping

# Start Redis
redis-server
```

**Permission Errors**:
```bash
# Fix Docker permissions
sudo usermod -aG docker $USER
# Log out and back in
```

### Docker Issues

**Clean Reset**:
```bash
# Stop all containers
docker compose down

# Remove volumes (⚠️ deletes data)
docker compose down -v

# Rebuild images
docker compose build --no-cache

# Start fresh
docker compose up
```

## Next Steps

After successful installation:

1. **[Configuration Guide](configuration.md)** - Set up your environment
2. **[First Run](first-run.md)** - Test your installation
3. **[Project Structure](../user-guide/project-structure.md)** - Understand the codebase

## Need Help?

If you encounter issues:

- Check the [GitHub Issues](https://github.com/benavlabs/fastapi-boilerplate/issues) for common problems
- Search [existing issues](https://github.com/benavlabs/fastapi-boilerplate/issues)
- Create a [new issue](https://github.com/benavlabs/fastapi-boilerplate/issues/new) with details 