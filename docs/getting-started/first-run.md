# First Run Guide

This guide walks you through verifying your installation, creating the admin user, and testing the main features.

## Verification Checklist

Before diving deeper, verify everything is working.

### 1. Check Services

=== "Docker Compose"

    ```bash
    docker compose ps
    ```

    You should see `web`, `db`, and `redis` services in `running` state.

=== "Local with uv"

    Verify Postgres and Redis are reachable:

    ```bash
    pg_isready -h localhost -p 5432
    redis-cli ping  # should print PONG
    ```

### 2. Test API Documentation

Open these in a browser:

- **Swagger UI**: <http://localhost:8000/docs>
- **ReDoc**: <http://localhost:8000/redoc>

### 3. Health Check

```bash
curl http://localhost:8000/health
```

Expected response:

```json
{
  "status": "healthy"
}
```

### 4. Database Tables

Check that tables were created:

=== "Docker Compose"

    ```bash
    docker compose exec db psql -U postgres -d postgres -c "\dt"
    ```

=== "Local with uv"

    ```bash
    psql -h localhost -U postgres -d postgres -c "\dt"
    ```

You should see tables like `user`, `tiers`, `rate_limits`, `api_keys`, `key_usage`, `key_permissions`.

## Initial Setup

Create the first admin user and the default tier.

!!! warning "Prerequisites"
    Make sure the database tables are created before running this. With `CREATE_TABLES_ON_STARTUP=true` (default), this happens automatically the first time the app boots.

### Create Admin User and Default Tier

The admin credentials come from `ADMIN_NAME`, `ADMIN_EMAIL`, `ADMIN_USERNAME`, and `ADMIN_PASSWORD` in `backend/.env`.

=== "Docker Compose"

    ```bash
    docker compose exec web python -m scripts.setup_initial_data
    ```

=== "Local with uv"

    ```bash
    cd backend
    uv run python -m scripts.setup_initial_data
    ```

This creates:

- A default tier (used as the fallback for new users)
- The admin user (with `is_superuser=true`)

## Testing Core Features

### Authentication Flow (Sessions)

This boilerplate uses **server-side sessions** with HTTP-only cookies — no JWT.

#### 1. Log In

```bash
curl -X POST "http://localhost:8000/api/v1/auth/login" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin&password=your_admin_password" \
  -c cookies.txt
```

Response sets an HTTP-only `session_id` cookie and returns a CSRF token:

```json
{ "id": 1, "username": "admin", "csrf_token": "..." }
```

`cookies.txt` now holds your session — pass it back with `-b cookies.txt` on subsequent requests.

#### 2. Get the Current User

```bash
curl http://localhost:8000/api/v1/users/me -b cookies.txt
```

#### 3. Create a New User

```bash
curl -X POST "http://localhost:8000/api/v1/users/" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "John Doe",
    "username": "johndoe",
    "email": "john@example.com",
    "password": "securepassword123"
  }'
```

(User creation is open — no auth required.)

#### 4. Check Auth Status

```bash
curl http://localhost:8000/api/v1/auth/check-auth -b cookies.txt
```

Returns `{"authenticated": true, "user": {...}, "session": {...}}` when logged in.

#### 5. Log Out

```bash
curl -X POST "http://localhost:8000/api/v1/auth/logout" -b cookies.txt -c cookies.txt
```

### API Keys

For programmatic access (machine-to-machine clients), create an API key while logged in:

```bash
curl -X POST "http://localhost:8000/api/v1/api-keys/" \
  -H "Content-Type: application/json" \
  -b cookies.txt \
  -d '{
    "name": "My Integration Key",
    "permissions": {},
    "usage_limits": {}
  }'
```

⚠️ **The full API key is shown once in the response.** Store it securely.

List your keys:

```bash
curl http://localhost:8000/api/v1/api-keys/ -b cookies.txt
```

### Tiers and Rate Limits

```bash
# List tiers
curl http://localhost:8000/api/v1/tiers/

# Get a tier by name
curl http://localhost:8000/api/v1/tiers/free

# List rate limits
curl http://localhost:8000/api/v1/rate-limits/
```

### Caching

Repeat a request twice and watch the timing — the second one should hit Redis:

```bash
curl http://localhost:8000/api/v1/users/johndoe -b cookies.txt -w "\nTime: %{time_total}s\n"
curl http://localhost:8000/api/v1/users/johndoe -b cookies.txt -w "\nTime: %{time_total}s\n"
```

### Background Tasks (Taskiq)

Background processing is enabled out of the box but no example endpoint ships with the starter. To register and dispatch your own task, see [Background Tasks](../user-guide/background-tasks/index.md).

To start a worker locally:

```bash
cd backend
uv run taskiq worker infrastructure.taskiq.worker:default_broker
```

## Adding Your First Feature Module

The codebase uses **vertical-slice modules** — each feature owns its models, schemas, CRUD, service, and routes in one folder under `backend/src/modules/`.

For a step-by-step walkthrough of adding a new module, see the [Development Guide](../user-guide/development.md).

## Debugging Common Issues

### Application Logs

=== "Docker Compose"

    ```bash
    docker compose logs -f web
    ```

=== "Local with uv"

    Logs are printed to stdout where `fastapi dev` is running.

### Database Logs

```bash
docker compose logs -f db
```

### Run Migrations Manually

If you need to re-run migrations:

```bash
cd backend
uv run alembic upgrade head
```

### Reset Everything (Docker)

```bash
cd backend
docker compose down -v   # ⚠️ wipes the database volume
docker compose up
```

## Next Steps

You've verified your install and tested the main features. Now:

### Essential Reading

1. **[Project Structure](../user-guide/project-structure.md)** - How the code is organized
2. **[Database Guide](../user-guide/database/index.md)** - Models, schemas, CRUD
3. **[Authentication](../user-guide/authentication/index.md)** - Sessions, OAuth, API keys

### Advanced Features

1. **[Caching](../user-guide/caching/index.md)** - Redis-backed cache
2. **[Background Tasks](../user-guide/background-tasks/index.md)** - Async jobs with Taskiq
3. **[Rate Limiting](../user-guide/rate-limiting/index.md)** - Per-tier rate limits

### Development Workflow

1. **[Development Guide](../user-guide/development.md)** - Extend the boilerplate
2. **[Testing](../user-guide/testing.md)** - Test your features
3. **[Production](../user-guide/production.md)** - Deploy

## Getting Help

- **Check the logs** for error messages
- **Verify your `backend/.env`** has the right values
- **Search [GitHub Issues](https://github.com/benavlabs/fastapi-boilerplate/issues)** for similar problems
- **Open a [new issue](https://github.com/benavlabs/fastapi-boilerplate/issues/new)** with details
