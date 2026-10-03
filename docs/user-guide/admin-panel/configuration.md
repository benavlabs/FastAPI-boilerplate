# Admin Panel Configuration

The admin panel has a deliberately small surface area: it's a [SQLAdmin](https://github.com/smithyhq/sqladmin) instance gated by a username/password from environment variables. Configuration boils down to a handful of `.env` values.

## Environment Variables

```env
# Toggle the admin panel (default: true)
ADMIN_ENABLED=true

# Admin login credentials — must BOTH be set, otherwise login always fails
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

1. The app factory calls the admin feature's `install(app)`, which the wiring lists among its installers
2. If `ADMIN_ENABLED=false`, the function returns `None` and the admin panel is **not mounted**
3. Otherwise, an `AdminAuth` backend is constructed using `SECRET_KEY`
4. A SQLAdmin `Admin` instance is created against the app's existing database `engine`
5. The views listed in `src/wiring/admin.py` are registered: `UserAdmin` and `TierAdmin`, each shipped by its own feature
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
        if not settings.ADMIN_USERNAME or not settings.ADMIN_PASSWORD:
            return False
        # constant-time comparison of username and password
        ...
```

Notes:

- Credentials come from environment variables, **not the database**. Restart the app to change them.
- **Admin login is disabled until both `ADMIN_USERNAME` and `ADMIN_PASSWORD` are set.** With the empty defaults, every login attempt fails — an empty form submission does not authenticate.
- Only one admin login is supported. There's no multi-admin user table.
- The session is signed with `SECRET_KEY` via the `SessionMiddleware` the panel mounts for itself.
- Logout clears the session: `request.session.clear()`.

If you need multiple admin operators, see [User Management](user-management.md) for ways to extend this.

## Mount Path

`ADMIN_BASE_URL` decides where the panel is mounted, and defaults to `/admin`:

```env
ADMIN_BASE_URL=/management
```

One setting feeds both the mount (`Admin(base_url=...)`) and the session cookie's `path`, so a panel
moved elsewhere keeps its login. Written with or without the slashes (`management`, `/management/`)
it comes out the same; a value that names no path at all is refused at startup.

Behind a proxy that serves the app under a prefix, the cookie follows the prefix too. A prefix set
with `--root-path /svc` reaches the app per request, so the panel scopes the cookie to the path the
request arrived through: `/svc/admin` with the default setting. Nothing needs configuring for that.

If you change it, also update any internal links in your frontend or operational docs.

!!! warning "Upgrading from a build before the cookie was scoped"

    Admin sessions created when the cookie had `path=/` keep being sent to every path until they
    expire (8 hours), and logging out only clears the cookie at the new path. Browsers send the
    longer-path cookie first and Starlette keeps the last value, so an old `path=/` cookie can
    outlive a logout. Clear the `admin_session` cookie in your browser once after upgrading, or
    change `SECRET_KEY` to invalidate every old admin session at once.

## Database Connection

SQLAdmin reuses the **same SQLAlchemy engine** the rest of the app uses (imported from `infrastructure/database/session.py`). There's no separate admin database connection or pool to configure.

## Session Cookies

The admin login uses Starlette's `SessionMiddleware`, which `AdminAuth` mounts on the panel's own
routes (`src/interfaces/admin/auth.py`). The API never carries it, so an API request never decodes
an admin cookie:

```python
self.middlewares = [
    Middleware(
        SessionMiddleware,
        secret_key=secret_key,
        session_cookie="admin_session",
        path=ADMIN_COOKIE_PATH,
        max_age=SESSION_MAX_AGE_SECONDS,
        same_site="lax",
        https_only=not local,
    )
]
```

Cookie behavior:

- HTTP-only, signed with `SECRET_KEY`, named `admin_session`
- Scoped to the panel's mount path (`ADMIN_BASE_URL`, plus the app's `root_path`), so it isn't sent with API requests
- Same-site `lax`
- `Secure` outside `local` and `development`, since nothing can revoke it server-side
- Expires after 8 hours (`SESSION_MAX_AGE_SECONDS`)

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
    Simplest. The admin panel never mounts. Run admin tasks via scripts (`uv run --no-sync python -m scripts.setup_initial_data`, custom one-offs) or temporary overrides.

2. **Restrict at the proxy/load balancer**
    Keep `ADMIN_ENABLED=true` but only allow the `/admin` path from your VPN's CIDR range or a specific IP allowlist. The app stays the same; the network blocks public access.

3. **Use a strong unique password**
    If you can't restrict at the network layer, treat `ADMIN_PASSWORD` like a production secret:
    - Pull from a secrets manager at deploy time, never commit
    - Rotate periodically
    - Use a long, high-entropy password (the production security validator refuses to start the app if `SECRET_KEY` is the placeholder, or if the admin panel is enabled with empty credentials; weak admin passwords are logged as warnings)

The Production Security Validator (`infrastructure/security/`) checks several things at startup when `ENVIRONMENT=production`, including that `ADMIN_USERNAME`/`ADMIN_PASSWORD` are set whenever `ADMIN_ENABLED=true`. Be deliberate about what you set.

## Environment Detection

The admin panel itself doesn't change behavior between `local` / `development` / `staging` / `production` — it's the same SQLAdmin app. What changes is the surrounding environment:

- **Cookie security**: `https_only` follows `ENVIRONMENT` — off in `local` and `development`, on everywhere else
- **Logging**: admin actions go through the same logger configured by `infrastructure/logging/`
- **Session backend**: the panel's cookie is self-contained and signed, not the API's `SESSION_BACKEND` (Redis/memory). Restart-resilience for the *admin* login isn't relevant — admins re-log-in fine.

## Troubleshooting

### `/admin` returns 404
Check `ADMIN_ENABLED`. If it's `false` (or unset and Pydantic resolves to a falsy value), the admin app isn't mounted. Verify with:

```bash
cd backend
uv run --no-sync python -c "from src.infrastructure.config.settings import get_settings; print(get_settings().ADMIN_ENABLED)"
```

### Login form keeps rejecting credentials
- Confirm `ADMIN_USERNAME` and `ADMIN_PASSWORD` in `backend/.env` match what you're typing
- Restart the app after changing env vars (settings are read at startup)
- If running in Docker, confirm the env vars are actually reaching the container (`docker compose exec api env | grep ADMIN_`)

### Admin session keeps logging out
The cookie expires 8 hours after login. To change that, edit `SESSION_MAX_AGE_SECONDS` in
`src/interfaces/admin/auth.py`:

```python
SESSION_MAX_AGE_SECONDS = 60 * 60 * 8
```

### Wrong `engine` connection / "no such table"
The admin uses the same engine as the API, which means it requires `CREATE_TABLES_ON_STARTUP=true` (default) or applied Alembic migrations. If `/admin` shows views but they're empty / error, check:

```bash
cd backend
uv run --no-sync alembic current
```

## Next Steps

- **[Adding Models](adding-models.md)** — Register your own models with the admin
- **[User Management](user-management.md)** — Extending admin authentication
- **[Production](../production.md)** — Production hardening checklist
