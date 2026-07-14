# Admin User Management

Admin authentication in this boilerplate is intentionally simple: a single admin user defined by environment variables, gated by `SECRET_KEY`-encrypted Starlette sessions. There's no admin user table, no multi-operator flow out of the box.

This page covers the trade-offs, hardening options, and what to do if you need something more sophisticated.

## How It Works

The admin login (`interfaces/admin/auth.py`) compares submitted credentials against `ADMIN_USERNAME` and `ADMIN_PASSWORD`:

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

On success, `admin_authenticated=True` is stored in a `SECRET_KEY`-encrypted Starlette session cookie. Subsequent requests check that flag.

There is no admin user model, no admin password hashing, no admin user table — credentials live in the environment.

## Initial Setup

In `backend/.env`:

```env
ADMIN_USERNAME=admin
ADMIN_PASSWORD=your-secure-password
SECRET_KEY=<openssl rand -hex 32>
```

Restart the app, navigate to <http://localhost:8000/admin>, and log in.

The same `ADMIN_*` env vars are also read by `scripts/setup_initial_data.py` to bootstrap the **first application superuser**, but the two systems are otherwise unrelated. See the next section for the distinction.

## Two Separate User Systems

The boilerplate maintains two completely separate concepts of "user". Don't confuse them.

| | Admin login | Application users |
|---|---|---|
| **Identifies** | An operator of the SQLAdmin panel | Your app's end users |
| **Storage** | Environment variables | Database (`user` table) |
| **Auth method** | Plaintext compare against `ADMIN_PASSWORD` | bcrypt-hashed password verified by sessions |
| **Multiple accounts?** | No (single `ADMIN_USERNAME`) | Yes (one row per user) |
| **Used by** | `/admin` only | `/api/v1/*` and `/admin` (the User model itself) |
| **Login URL** | `/admin/login` | `/api/v1/auth/login` |

A user with `is_superuser=true` in the application database can call superuser-only API endpoints (e.g. `DELETE /api/v1/users/db/{username}`). They **cannot** log into the admin panel unless their credentials happen to match `ADMIN_USERNAME` / `ADMIN_PASSWORD`. The two systems don't share state.

## Managing Application Users via the Admin

Once logged in to `/admin`:

- **Users** view: create / edit / delete application users (goes against the `user` table)
- **Tiers** view: assign tiers, edit names and descriptions
- Password fields go through `on_model_change` for automatic hashing
- Toggle `is_superuser` directly in the edit form

The `/admin` panel is the easiest way to grant superuser status to an existing application user.

## Hardening for Production

### Option 1: Disable in Production

The simplest move: don't expose the admin panel at all in production.

```env
ADMIN_ENABLED=false
```

`create_admin_interface()` short-circuits when this is false, and nothing is mounted. Run admin tasks via scripts or DB tools instead.

### Option 2: Network-Restrict the Path

Keep `ADMIN_ENABLED=true` but allow `/admin/*` only from your VPN or office IP range at the load balancer / reverse proxy. The app stays the same; the network blocks public access.

This is usually the right call when you need occasional access without baking new admin code paths.

### Option 3: Strong Credentials + TLS

If you need `/admin` reachable from the internet:

- Generate a long, high-entropy `ADMIN_PASSWORD` and pull it from a secrets manager at deploy time
- Use HTTPS (terminate at your proxy)
- Enable secure cookies if you serve over HTTPS — see [Configuration](configuration.md#session-cookies)
- Rotate the password periodically (requires a deploy)

The production security validator (`infrastructure/security/`) does **not** check admin credentials specifically — it only catches the placeholder `SECRET_KEY`, `DEBUG=true`, and `CORS_ORIGINS=*`. You're responsible for the strength of `ADMIN_PASSWORD`.

## Recovering from a Lost Admin Password

Since admin credentials are env vars, recovery is mechanical:

1. Edit `backend/.env` (or your secrets manager / orchestrator config) to set new `ADMIN_USERNAME` / `ADMIN_PASSWORD`
2. Restart the app

There's no database row to fix. There's no email-based reset flow either — these credentials aren't meant to be self-service.

## When You Need Multiple Admins

The single-credential design works for small teams or solo deployments. If you need real multi-operator admin auth, you have a few options:

### Option A: Use Application Superusers + a Dedicated Admin Route

Skip the SQLAdmin login entirely. Restrict `/admin` access to authenticated app users with `is_superuser=true` by writing a custom `AuthenticationBackend`:

```python
# interfaces/admin/auth.py
from sqladmin.authentication import AuthenticationBackend
from starlette.requests import Request

# Pseudocode — wire to your existing session backend
class AdminAuth(AuthenticationBackend):
    async def login(self, request: Request) -> bool:
        # Reuse your /api/v1/auth/login flow:
        # validate credentials, look up the user, check is_superuser
        ...

    async def authenticate(self, request: Request) -> bool:
        # Read the app's session_id cookie, validate it, confirm is_superuser
        ...
```

Trade-offs: now any app superuser can log in. You also need to think about CSRF (the app uses double-submit; SQLAdmin posts forms separately).

### Option B: Add an `AdminUser` Model

Build a small model (`AdminUser` with `username`, `hashed_password`, `is_active`) and override `AdminAuth.login` to query it. Add a one-off script to seed admin users.

### Option C: External Auth (OIDC / SAML)

For larger orgs, mount the admin behind an SSO proxy (Authelia, Pomerium, AWS ALB with Cognito). The admin app trusts the proxy's authentication header and grants access on its presence.

None of these are wired up in the boilerplate — pick the one that fits your environment and implement it. The SQLAdmin docs cover [Authentication](https://github.com/smithyhq/sqladmin) extensions in detail.

## Auditing Admin Activity

The admin panel doesn't log every action by default. If you need an audit trail:

- The boilerplate's logging infrastructure (`infrastructure/logging/`) gives you correlation IDs out of the box. SQLAdmin requests pass through it like any other.
- Override `on_model_change` / `after_model_change` / `delete_model` in your views to log explicitly:

```python
from src.infrastructure.logging import get_logger

logger = get_logger()


class UserAdmin(DataclassModelMixin, ModelView, model=User):
    async def on_model_change(self, data, model, is_created, request):
        action = "created" if is_created else "updated"
        logger.info(f"Admin {action} user", extra={"user_id": data.get("id"), "actor": "admin"})
```

For richer auditing, write to a dedicated log stream or push events to a SIEM.

## Key Files

| Component | Location |
|-----------|----------|
| Admin auth backend | `backend/src/interfaces/admin/auth.py` |
| Admin app factory | `backend/src/interfaces/admin/initialize.py` |
| Settings classes | `backend/src/infrastructure/config/settings.py` (`AdminSettings`, `SQLAdminSettings`) |
| Initial data script | `backend/scripts/setup_initial_data.py` |

## Next Steps

- **[Configuration](configuration.md)** — Environment variables and cookie behavior
- **[Adding Models](adding-models.md)** — Register your own admin views
- **[Permissions](../authentication/permissions.md)** — Application-level superuser checks
- **[Production](../production.md)** — Production hardening checklist
