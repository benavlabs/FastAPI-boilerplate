# Admin Panel Configuration

The admin panel has a deliberately small surface area: it's a [SQLAdmin](https://aminalaee.dev/sqladmin/) instance gated by a username/password from environment variables. Configuration boils down to a handful of `.env` values.

## Environment Variables

```env
# Toggle the admin panel (default: true)
ADMIN_ENABLED=true

# Admin login credentials
ADMIN_USERNAME=admin
ADMIN_PASSWORD=your-secure-password

# Used for admin session encryption (same SECRET_KEY as the rest of the app)
SECRET_KEY=<openssl rand -hex 32>
```

That's the whole admin-specific config. Everything else (engine, models, mount path) is hardcoded in `src/interfaces/admin/initialize.py` for simplicity.

### Backing Settings Classes

The variables map to two settings classes in `src/infrastructure/config/settings.py`:

- **`AdminSettings`** — `ADMIN_NAME`, `ADMIN_EMAIL`, `ADMIN_USERNAME`, `ADMIN_PASSWORD`, `DEFAULT_TIER_NAME`. Used by both the admin panel login *and* `scripts/setup_initial_data.py` to bootstrap the first superuser.
- **`SQLAdminSettings`** — `ADMIN_ENABLED`. Single toggle for the admin panel.

## What Happens at Startup

1. `interfaces/main.py` calls `create_admin_interface(app)` from `interfaces/admin/initialize.py`
2. If `ADMIN_ENABLED=false`, the function returns `None` and the admin panel is **not mounted**
3. Otherwise, an `AdminAuth` backend is constructed using `SECRET_KEY`
4. A SQLAdmin `Admin` instance is created against the app's existing database `engine`
5. `register_admin_views(admin)` adds `UserAdmin` and `TierAdmin` (from `views/`)
6. The admin app is mounted at `/admin`

## Login Authentication

Login flow (in `interfaces/admin/auth.py`):

```python
class AdminAuth(AuthenticationBackend):
    async def login(self, request: Request) -> bool:
        form = await request.form()
        username = form.get("username")
        password = form.get("password")

        settings = get_settings()
        if username == settings.ADMIN_USERNAME and password == settings.ADMIN_PASSWORD:
            request.session.update({"admin_authenticated": True})
            return True
        return False
```

Notes:

- Credentials come from environment variables, **not the database**. Restart the app to change them.
- Only one admin login is supported. There's no multi-admin user table.
- The session is encrypted with `SECRET_KEY` via Starlette's `SessionMiddleware`.
- Logout clears the session: `request.session.clear()`.

If you need multiple admin operators, see [User Management](user-management.md) for ways to extend this.

## Mount Path

The admin panel is hardcoded at `/admin` (defined when `Admin(...)` is instantiated). To change the path, edit `src/interfaces/admin/initialize.py`:

```python
admin = Admin(
    app=app,
    engine=engine,
    authentication_backend=authentication_backend,
    title="Admin",
    base_url="/management",   # add this to change the mount path
)
```

If you change it, also update any internal links in your frontend or operational docs.

## Database Connection

SQLAdmin reuses the **same SQLAlchemy engine** the rest of the app uses (imported from `infrastructure/database/session.py`). There's no separate admin database connection or pool to configure.

## Session Cookies

The admin login uses Starlette's `SessionMiddleware`, which is added to the FastAPI app in `src/interfaces/main.py`:

```python
app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)
```

Cookie behavior:

- HTTP-only by default
- Encrypted/signed with `SECRET_KEY`
- Same-site `lax`
- **Not** marked `Secure` automatically — if you serve the app over HTTPS, set `SESSION_SECURE_COOKIES=true` and adjust the middleware as needed (the Starlette `SessionMiddleware` doesn't have a built-in production-secure flag the way our session backend does)

For production behind HTTPS, you'll typically want to:

1. Terminate TLS at the proxy / load balancer
2. Strip `/admin` from public-facing routing entirely (see [Production Hardening](#production-hardening) below)

## Development vs Production

### Development

The default `.env.example` is already development-ready:

```env
ENVIRONMENT=development
ADMIN_ENABLED=true
ADMIN_USERNAME=admin
ADMIN_PASSWORD=your-secure-password
SECRET_KEY=insecure-secret-key-change-this-in-production
```

Open <http://localhost:8000/admin>, log in, and you have access to Users and Tiers.

### Production Hardening

Three options, ordered by aggressiveness:

1. **Disable entirely**
    ```env
    ADMIN_ENABLED=false
    ```
    Simplest. The admin panel never mounts. Run admin tasks via scripts (`uv run python -m scripts.setup_initial_data`, custom one-offs) or temporary overrides.

2. **Restrict at the proxy/load balancer**
    Keep `ADMIN_ENABLED=true` but only allow the `/admin` path from your VPN's CIDR range or a specific IP allowlist. The app stays the same; the network blocks public access.

3. **Use a strong unique password**
    If you can't restrict at the network layer, treat `ADMIN_PASSWORD` like a production secret:
    - Pull from a secrets manager at deploy time, never commit
    - Rotate periodically
    - Use a long, high-entropy password (the production security validator will refuse to start the app if `SECRET_KEY` is the placeholder, but it doesn't validate `ADMIN_PASSWORD`)

The Production Security Validator (`infrastructure/security/`) checks several things at startup when `ENVIRONMENT=production`, but admin credentials aren't currently in the validation list. Be deliberate about what you set.

## Environment Detection

The admin panel itself doesn't change behavior between `local` / `development` / `staging` / `production` — it's the same SQLAdmin app. What changes is the surrounding environment:

- **Cookie security**: derived from your reverse proxy / TLS setup, not from the `ENVIRONMENT` setting
- **Logging**: admin actions go through the same logger configured by `infrastructure/logging/`
- **Session backend**: Starlette's `SessionMiddleware` is in-memory + cookie-based, not the same as the API's `SESSION_BACKEND` (Redis/memcached/memory). Restart-resilience for the *admin* login isn't relevant — admins re-log-in fine.

## Troubleshooting

### `/admin` returns 404
Check `ADMIN_ENABLED`. If it's `false` (or unset and Pydantic resolves to a falsy value), the admin app isn't mounted. Verify with:

```bash
cd backend
uv run python -c "from src.infrastructure.config.settings import get_settings; print(get_settings().ADMIN_ENABLED)"
```

### Login form keeps rejecting credentials
- Confirm `ADMIN_USERNAME` and `ADMIN_PASSWORD` in `backend/.env` match what you're typing
- Restart the app after changing env vars (settings are read at startup)
- If running in Docker, confirm the env vars are actually reaching the container (`docker compose exec app env | grep ADMIN_`)

### Admin session keeps logging out
The Starlette `SessionMiddleware` cookie's lifetime is controlled by the browser (it's a session cookie). For longer-lived admin sessions, edit the middleware setup in `src/interfaces/main.py` to pass `max_age=...`:

```python
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.SECRET_KEY,
    max_age=60 * 60 * 8,  # 8 hours
)
```

### Wrong `engine` connection / "no such table"
The admin uses the same engine as the API, which means it requires `CREATE_TABLES_ON_STARTUP=true` (default) or applied Alembic migrations. If `/admin` shows views but they're empty / error, check:

```bash
cd backend
uv run alembic current
```

## Next Steps

- **[Adding Models](adding-models.md)** — Register your own models with the admin
- **[User Management](user-management.md)** — Extending admin authentication
- **[Production](../production.md)** — Production hardening checklist
