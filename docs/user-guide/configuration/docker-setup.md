# Docker Setup

Learn how to configure and run the FastAPI Boilerplate using Docker Compose. The project includes a complete containerized setup with PostgreSQL, Redis, background workers, and optional services.

## Docker Compose Architecture

The boilerplate includes these core services:

```yaml
services:
  web:          # FastAPI application (uvicorn or gunicorn)
  worker:       # ARQ background task worker  
  db:           # PostgreSQL 13 database
  redis:        # Redis Alpine for caching/queues
  # Optional services (commented out by default):
  # pgadmin:    # Database administration
  # nginx:      # Reverse proxy
  # create_superuser: # One-time superuser creation
  # create_tier:      # One-time tier creation
```

## Basic Docker Compose

### Main Configuration

The main `docker-compose.yml` includes:

```yaml
version: '3.8'

services:
  web:
    build:
      context: .
      dockerfile: Dockerfile
    # Development mode (reload enabled)
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
    # Production mode (uncomment for production)
    # command: gunicorn app.main:app -w 4 -k uvicorn.workers.UvicornWorker -b 0.0.0.0:8000
    env_file:
      - ./src/.env
    ports:
      - "8000:8000"
    depends_on:
      - db
      - redis
    volumes:
      - ./src/app:/code/app
      - ./src/.env:/code/.env

  worker:
    build:
      context: .
      dockerfile: Dockerfile
    command: arq app.core.worker.settings.WorkerSettings
    env_file:
      - ./src/.env
    depends_on:
      - db
      - redis
    volumes:
      - ./src/app:/code/app
      - ./src/.env:/code/.env

  db:
    image: postgres:13
    env_file:
      - ./src/.env
    volumes:
      - postgres-data:/var/lib/postgresql/data
    expose:
      - "5432"

  redis:
    image: redis:alpine
    volumes:
      - redis-data:/data
    expose:
      - "6379"

volumes:
  postgres-data:
  redis-data:
```

### Environment File Loading

All services automatically load environment variables from `./src/.env`:

```yaml
env_file:
  - ./src/.env
```

The Docker services use these environment variables:

- `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` for database
- `REDIS_*_HOST` variables automatically resolve to service names
- All application settings from your `.env` file

## Service Details

### Web Service (FastAPI Application)

The web service runs your FastAPI application:

```yaml
web:
  build:
    context: .
    dockerfile: Dockerfile
  # Development: uvicorn with reload
  command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
  # Production: gunicorn with multiple workers (commented out)
  # command: gunicorn app.main:app -w 4 -k uvicorn.workers.UvicornWorker -b 0.0.0.0:8000
  env_file:
    - ./src/.env
  ports:
    - "8000:8000"  # Direct access in development
  volumes:
    - ./src/app:/code/app  # Live code reloading
    - ./src/.env:/code/.env
```

**Key Features:**

- **Development mode**: Uses uvicorn with `--reload` for automatic code reloading
- **Production mode**: Switch to gunicorn with multiple workers (commented out)
- **Live reloading**: Source code mounted as volume for development
- **Port exposure**: Direct access on port 8000 (can be disabled for nginx)

### Worker Service (Background Tasks)

Handles background job processing with ARQ:

```yaml
worker:
  build:
    context: .
    dockerfile: Dockerfile
  command: arq app.core.worker.settings.WorkerSettings
  env_file:
    - ./src/.env
  depends_on:
    - db
    - redis
  volumes:
    - ./src/app:/code/app
    - ./src/.env:/code/.env
```

**Features:**
- Runs ARQ worker for background job processing
- Shares the same codebase and environment as web service
- Automatically connects to Redis for job queues
- Live code reloading in development

### Database Service (PostgreSQL 13)

```yaml
db:
  image: postgres:13
  env_file:
    - ./src/.env
  volumes:
    - postgres-data:/var/lib/postgresql/data
  expose:
    - "5432"  # Internal network only
```

**Configuration:**
- Uses environment variables: `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`
- Data persisted in named volume `postgres-data`
- Only exposed to internal Docker network (no external port)
- To enable external access, uncomment the ports section

### Redis Service

```yaml
redis:
  image: redis:alpine
  volumes:
    - redis-data:/data
  expose:
    - "6379"  # Internal network only
```

**Features:**
- Lightweight Alpine Linux image
- Data persistence with named volume
- Used for caching, job queues, and rate limiting
- Internal network access only

## Optional Services

### Database Administration (pgAdmin)

Uncomment to enable web-based database management:

```yaml
pgadmin:
  container_name: pgadmin4
  image: dpage/pgadmin4:latest
  restart: always
  ports:
    - "5050:80"
  volumes:
    - pgadmin-data:/var/lib/pgadmin
  env_file:
    - ./src/.env
  depends_on:
    - db
```

**Usage:**
- Access at `http://localhost:5050`
- Requires `PGADMIN_DEFAULT_EMAIL` and `PGADMIN_DEFAULT_PASSWORD` in `.env`
- Connect to database using service name `db` and port `5432`

### Reverse Proxy (Nginx)

Uncomment for production-style reverse proxy:

```yaml
nginx:
  image: nginx:latest
  ports:
    - "80:80"
  volumes:
    - ./default.conf:/etc/nginx/conf.d/default.conf
  depends_on:
    - web
```

**Configuration:**
The included `default.conf` provides:

```nginx
server {
    listen 80;
    
    location / {
        proxy_pass http://web:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

**When using nginx:**

1. Uncomment the nginx service
2. Comment out the `ports` section in the web service
3. Uncomment `expose: ["8000"]` in the web service

### Initialization Services

#### Create First Superuser

```yaml
create_superuser:
  build:
    context: .
    dockerfile: Dockerfile
  env_file:
    - ./src/.env
  depends_on:
    - db
    - web
  command: python -m src.scripts.create_first_superuser
  volumes:
    - ./src:/code/src
```

#### Create First Tier

```yaml
create_tier:
  build:
    context: .
    dockerfile: Dockerfile
  env_file:
    - ./src/.env
  depends_on:
    - db
    - web
  command: python -m src.scripts.create_first_tier
  volumes:
    - ./src:/code/src
```

**Usage:**

- These are one-time setup services
- Uncomment when you need to initialize data
- Run once, then comment out again

## Dockerfile Details

The project uses a multi-stage Dockerfile with `uv` for fast Python package management:

### Builder Stage

```dockerfile
FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim AS builder

ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

WORKDIR /app

# Install dependencies (cached layer)
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project

# Copy and install project
COPY . /app
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-editable
```

### Final Stage

```dockerfile
FROM python:3.11-slim-bookworm

# Create non-root user for security
RUN groupadd --gid 1000 app \
    && useradd --uid 1000 --gid app --shell /bin/bash --create-home app

# Copy virtual environment from builder
COPY --from=builder --chown=app:app /app/.venv /app/.venv

ENV PATH="/app/.venv/bin:$PATH"
USER app
WORKDIR /code

# Default command (can be overridden)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
```

**Security Features:**

- Non-root user execution
- Multi-stage build for smaller final image
- Cached dependency installation

## Common Docker Commands

### Development Workflow

```bash
# Start all services
docker compose up

# Start in background
docker compose up -d

# Rebuild and start (after code changes)
docker compose up --build

# View logs
docker compose logs -f web
docker compose logs -f worker

# Stop services
docker compose down

# Stop and remove volumes (reset data)
docker compose down -v
```

### Service Management

```bash
# Start specific services
docker compose up web db redis

# Scale workers
docker compose up --scale worker=3

# Execute commands in running containers
docker compose exec web bash
docker compose exec db psql -U postgres
docker compose exec redis redis-cli

# View service status
docker compose ps
```

### Production Mode

To switch to production mode:

1. **Enable Gunicorn:**
   ```yaml
   # Comment out uvicorn line
   # command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
   # Uncomment gunicorn line
   command: gunicorn app.main:app -w 4 -k uvicorn.workers.UvicornWorker -b 0.0.0.0:8000
   ```

2. **Enable Nginx** (optional):
   ```yaml
   # Uncomment nginx service
   nginx:
     image: nginx:latest
     ports:
       - "80:80"
   
   # In web service, comment out ports and uncomment expose
   # ports:
   #   - "8000:8000"
   expose:
     - "8000"
   ```

3. **Remove development volumes:**
   ```yaml
   # Remove or comment out for production
   # volumes:
   #   - ./src/app:/code/app
   #   - ./src/.env:/code/.env
   ```

## Environment Configuration

### Service Communication

Services communicate using service names:

```yaml
# In your .env file for Docker
POSTGRES_SERVER=db      # Not localhost
REDIS_CACHE_HOST=redis  # Not localhost
REDIS_QUEUE_HOST=redis
REDIS_RATE_LIMIT_HOST=redis
```

### Port Management

**Development (default):**
- Web: `localhost:8000` (direct access)
- Database: `localhost:5432` (uncomment ports to enable)
- Redis: `localhost:6379` (uncomment ports to enable)
- pgAdmin: `localhost:5050` (if enabled)

**Production with Nginx:**
- Web: `localhost:80` (through nginx)
- Database: Internal only
- Redis: Internal only

## Troubleshooting

### Common Issues

**Container won't start:**
```bash
# Check logs
docker compose logs web

# Rebuild image
docker compose build --no-cache web

# Check environment file
docker compose exec web env | grep POSTGRES
```

**Database connection issues:**
```bash
# Check if db service is running
docker compose ps db

# Test connection from web container
docker compose exec web ping db

# Check database logs
docker compose logs db
```

**Port conflicts:**
```bash
# Check what's using the port
lsof -i :8000

# Use different ports
ports:
  - "8001:8000"  # Use port 8001 instead
```

### Development vs Production

**Development features:**

- Live code reloading with volume mounts
- Direct port access
- uvicorn with `--reload`
- Exposed database/redis ports for debugging

**Production optimizations:**

- No volume mounts (code baked into image)
- Nginx reverse proxy
- Gunicorn with multiple workers
- Internal service networking only
- Resource limits and health checks

## Best Practices

### Development
- Use volume mounts for live code reloading
- Enable direct port access for debugging
- Use uvicorn with reload for fast development
- Enable optional services (pgAdmin) as needed

### Production
- Switch to gunicorn with multiple workers
- Use nginx for reverse proxy and load balancing
- Remove volume mounts and bake code into images
- Use internal networking only
- Set resource limits and health checks

### Security
- Containers run as non-root user
- Use internal networking for service communication
- Don't expose database/redis ports externally
- Use Docker secrets for sensitive data in production

### Monitoring
- Use `docker compose logs` to monitor services
- Set up health checks for all services
- Monitor resource usage with `docker stats`
- Use structured logging for better observability

The Docker setup provides everything you need for both development and production. Start with the default configuration and customize as your needs grow! 