# Installation Guide

This guide covers different ways to install the FastAPI Boilerplate depending on your needs.

## System Requirements

- **Python**: 3.11 or higher
- **Operating System**: Linux, macOS, or Windows (WSL2 recommended)
- **Memory**: 4GB RAM minimum (8GB recommended)
- **Disk Space**: ~2GB free

## Method 1: Docker Compose (Recommended)

Docker Compose handles every service for you (Postgres + Redis + the app).

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/) (20.10+)
- [Docker Compose](https://docs.docker.com/compose/install/) (v2+)

### Steps

1. **Clone the repository**:

    ```bash
    git clone https://github.com/benavlabs/fastapi-boilerplate
    cd fastapi-boilerplate/backend
    ```

2. **Set up the environment file**:

    ```bash
    cp .env.example .env
    # Edit .env: set SECRET_KEY, change default DB password, etc.
    ```

3. **Bring up the stack**:

    ```bash
    docker compose up
    ```

4. **Verify it's running**:

    ```bash
    curl http://localhost:8000/health
    ```

### What Gets Installed

- **App** (FastAPI + Uvicorn) on port 8000
- **PostgreSQL** on port 5432
- **Redis** on port 6379

## Method 2: Manual Installation (Local with uv)

For development on your host machine. You provide PostgreSQL and Redis yourself.

### Prerequisites

1. **Python 3.11+**:

    ```bash
    # Ubuntu/Debian
    sudo apt update && sudo apt install python3.11

    # macOS
    brew install python@3.11

    # Windows: download from python.org
    ```

2. **uv** (fast Python package manager):

    ```bash
    # macOS / Linux
    curl -LsSf https://astral.sh/uv/install.sh | sh

    # or via pip
    pip install uv
    ```

3. **PostgreSQL**:

    ```bash
    # Ubuntu/Debian
    sudo apt install postgresql postgresql-contrib

    # macOS
    brew install postgresql
    ```

4. **Redis**:

    ```bash
    # Ubuntu/Debian
    sudo apt install redis-server

    # macOS
    brew install redis
    ```

### Steps

1. **Clone the repository**:

    ```bash
    git clone https://github.com/benavlabs/fastapi-boilerplate
    cd fastapi-boilerplate
    ```

    The repo is a [uv workspace](https://docs.astral.sh/uv/concepts/projects/workspaces/) — the deployable application lives in `backend/` and the developer CLI (`bp`) lives in `cli/`. Both share a single virtual environment at the repo root.

2. **Install Python dependencies**:

    ```bash
    uv sync --all-packages --all-extras
    ```

    This syncs the whole workspace — backend, CLI, and dev tools — into one `.venv/` at the repo root. From here on, `uv run <cmd>` works from any subdirectory.

3. **Set up environment variables**:

    ```bash
    cp backend/.env.example backend/.env
    # Edit backend/.env: point POSTGRES_SERVER and CACHE_REDIS_HOST at localhost,
    # set a strong SECRET_KEY (or run `uv run bp env gen-secret`), etc.
    ```

    The CLI ships a few helpers for this step — see [CLI → Commands](../cli/commands.md):

    ```bash
    uv run bp env gen-secret      # print a fresh SECRET_KEY
    uv run bp env validate        # audit the .env against the production validator
    ```

4. **Set up PostgreSQL** (if not already configured):

    ```bash
    sudo -u postgres psql
    CREATE DATABASE myapp;
    CREATE USER myuser WITH PASSWORD 'mypassword';
    GRANT ALL PRIVILEGES ON DATABASE myapp TO myuser;
    \q
    ```

5. **Run database migrations** (from `backend/` — alembic looks for `alembic.ini` in cwd):

    ```bash
    cd backend
    uv run alembic upgrade head
    ```

6. **Create the initial admin user and tier**:

    ```bash
    uv run python -m scripts.setup_initial_data
    ```

7. **Start the app**:

    ```bash
    uv run fastapi dev src/interfaces/main.py
    ```

8. **(Optional) Start a Taskiq worker** (in a second terminal):

    ```bash
    uv run taskiq worker infrastructure.taskiq.worker:default_broker
    ```

## Method 3: Development Setup

For contributors and anyone modifying the boilerplate itself.

### Steps

1. **Fork and clone**:

    ```bash
    # Fork on GitHub first
    git clone https://github.com/yourusername/fastapi-boilerplate
    cd fastapi-boilerplate
    ```

2. **Install dev dependencies**:

    ```bash
    uv sync --all-packages --all-extras
    ```

3. **Set up pre-commit hooks** (from the repo root):

    ```bash
    uv run --project backend pre-commit install
    ```

4. **Set up the environment**:

    ```bash
    cp backend/.env.example backend/.env
    ```

5. **Run the test suite to verify your setup**:

    ```bash
    uv run pytest
    ```

## Configuration

### Environment Variables

The app reads its configuration from `backend/.env` (see `backend/.env.example` for the full reference). Common variables:

```env
# Environment
ENVIRONMENT=development

# Database
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
POSTGRES_DB=postgres
POSTGRES_SERVER=db        # use "localhost" without Docker
POSTGRES_PORT=5432

# Cache (Redis)
CACHE_BACKEND=redis
CACHE_REDIS_HOST=redis    # use "localhost" without Docker
CACHE_REDIS_PORT=6379

# Security
SECRET_KEY=insecure-change-this-in-production

# Initial admin
ADMIN_NAME=Admin User
ADMIN_EMAIL=admin@example.com
ADMIN_USERNAME=admin
ADMIN_PASSWORD=your-secure-password
```

See [Environment Variables](../user-guide/configuration/environment-variables.md) for the complete reference.

### Using a hosted database instead

You don't have to run Postgres yourself. Set `DATABASE_URL` and it overrides every `POSTGRES_*` variable above — the local container (or local install) becomes unnecessary:

```env
DATABASE_URL=postgresql+asyncpg://user:password@host.example.com/dbname?ssl=require
```

[Neon](../user-guide/database/neon.md) — serverless Postgres, and a sponsor of this project — is free to start (a permanent free plan, no credit card) and has a step-by-step guide here, including the connection-string conversion asyncpg needs. Any managed Postgres works the same way.

## Verification

After installing, verify everything works:

1. **API Docs**: <http://localhost:8000/docs>
2. **Health Check**: `curl http://localhost:8000/health`
3. **Admin Panel**: <http://localhost:8000/admin>
4. **Database**: check the app log for "Database connected" / no errors at startup

## Troubleshooting

### Port Already in Use

```bash
# Find what's on port 8000
lsof -i :8000
kill -9 <PID>
```

### Database Connection Error

```bash
# Linux
sudo systemctl status postgresql
sudo systemctl restart postgresql

# macOS (Homebrew)
brew services restart postgresql
```

### Redis Connection Error

```bash
redis-cli ping  # should print PONG
# If not, start it:
redis-server
```

### Docker — Clean Reset

```bash
cd backend
docker compose down       # stop containers
docker compose down -v    # also delete volumes (⚠️ wipes data)
docker compose build --no-cache
docker compose up
```

## Next Steps

1. **[Configuration Guide](configuration.md)** - Set up your environment
2. **[First Run](first-run.md)** - Test your installation
3. **[Project Structure](../user-guide/project-structure.md)** - Understand the codebase

## Need Help?

- Check the [GitHub Issues](https://github.com/benavlabs/fastapi-boilerplate/issues) for known problems
- Open a [new issue](https://github.com/benavlabs/fastapi-boilerplate/issues/new) with details
