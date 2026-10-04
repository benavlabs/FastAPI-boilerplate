# Getting Started

Welcome to the FastAPI Boilerplate! This guide will have you up and running in just a few minutes.

## Quick Start (5 minutes)

Pick whichever workflow fits you:

=== "Local with uv"

    ### Prerequisites

    - [uv](https://docs.astral.sh/uv/getting-started/installation/) (0.4+)
    - PostgreSQL and Redis running locally (or use the Docker tab)

    ### 1. Get the Template

    1. Click **"Use this template"** on the [GitHub repository](https://github.com/benavlabs/fastapi-boilerplate)
    2. Create a new repository with your project name
    3. Clone your new repository and `cd` into the backend:

    ```bash
    git clone https://github.com/yourusername/your-project-name
    cd your-project-name/backend
    ```

    ### 2. Install Dependencies

    ```bash
    uv sync --all-packages --all-extras
    ```

    From the repository root: `--all-packages` installs both workspace members and
    `--all-extras` adds the dev tools (ruff, mypy, pytest).

    ### 3. Environment Setup

    ```bash
    cp .env.example .env
    # then edit .env to set your database creds, SECRET_KEY, etc.
    ```

    !!! warning "SECRET_KEY"
        Generate a secure key with `python -c "import secrets; print(secrets.token_urlsafe(64))"` and replace the default value in `.env`.

    ### 4. Run the Server

    ```bash
    uv run --no-sync fastapi dev src/interfaces/main.py
    ```

=== "Docker Compose"

    ### Prerequisites

    - [Docker](https://docs.docker.com/get-docker/) (20.10+)
    - [Docker Compose](https://docs.docker.com/compose/install/) (v2+)

    ### 1. Get the Template

    ```bash
    git clone https://github.com/yourusername/your-project-name
    cd your-project-name/backend
    ```

    ### 2. Environment Setup

    ```bash
    cp .env.example .env
    # then edit .env to set your DB password, SECRET_KEY, etc.
    ```

    ### 3. Start Everything

    ```bash
    docker compose up
    ```

    This brings up:

    - **FastAPI app** on port 8000
    - **PostgreSQL** database
    - **Redis** for cache, rate limiting, and sessions

## Verify It's Running

Visit:

- **Swagger UI**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc**: [http://localhost:8000/redoc](http://localhost:8000/redoc)
- **Health Check**: [http://localhost:8000/health](http://localhost:8000/health)

## You're Ready!

You now have a working FastAPI app with:

- REST API with automatic OpenAPI docs
- PostgreSQL database with Alembic migrations
- Redis-backed cache and rate limiting
- Session-based authentication with optional OAuth (Google, GitHub)
- API keys with per-key permissions
- SQLAdmin admin interface at `/admin`
- Async background task support via Taskiq

## Test Your API

### 1. Health Check

```bash
curl http://localhost:8000/health
```

### 2. Create a User

```bash
curl -X POST "http://localhost:8000/api/v1/users/" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "John Doe",
    "username": "johndoe",
    "email": "john@example.com",
    "password": "securepassword"
  }'
```

### 3. Log In (Session Cookie)

```bash
curl -X POST "http://localhost:8000/api/v1/auth/login" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=johndoe&password=securepassword" \
  -c cookies.txt
```

The response sets an HTTP-only session cookie and returns a CSRF token. Use `-b cookies.txt` on subsequent requests to send the session along.

### 4. Get the Current User

```bash
curl http://localhost:8000/api/v1/users/me -b cookies.txt
```

## Next Steps

### Essential Reading

- **[Configuration Guide](configuration.md)** - Environment variables and settings
- **[Project Structure](../user-guide/project-structure.md)** - How the code is organized
- **[Authentication](../user-guide/authentication/index.md)** - Sessions, OAuth, and API keys

### Popular Features

- **[Database Operations](../user-guide/database/index.md)** - Models, schemas, and CRUD
- **[Caching](../user-guide/caching/index.md)** - Redis-backed caching
- **[Background Tasks](../user-guide/background-tasks/index.md)** - Async jobs with Taskiq
- **[Rate Limiting](../user-guide/rate-limiting/index.md)** - Protect your API from abuse

### Development & Deployment

- **[Development Guide](../user-guide/development.md)** - Extend and customize
- **[Testing](../user-guide/testing.md)** - Write tests for your API
- **[Production Deployment](../user-guide/production.md)** - Deploy to production

## Alternative Setup Methods

- **[Manual Installation](installation.md)** - Step-by-step setup details

## Need Help?

- Join our **[Discord Community](../community.md)** - Get help from other developers
- Report issues on **[GitHub](https://github.com/benavlabs/fastapi-boilerplate/issues)**

---

**Ready to dive deeper?** Continue with the [installation guide](installation.md) or jump to the [user guide](../user-guide/index.md).
