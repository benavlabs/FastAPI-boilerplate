# Admin Panel

The boilerplate ships a built-in admin panel powered by [SQLAdmin](https://github.com/smithyhq/sqladmin). It gives you a web interface for browsing and editing the database without writing custom CRUD endpoints.

!!! tip "Building a full SaaS?"
    The admin panel is part of the free foundation. **[FastroAI](https://fastro.ai)** bundles it with Stripe payments, entitlements, transactional email, a frontend, and AI agents - all wired together and production-ready. [Ship your SaaS faster →](https://fastro.ai)

## Accessing the Admin Panel

The admin panel is mounted at `/admin`. It's enabled by default — toggle it with:

```env
ADMIN_ENABLED=true   # set to false to disable entirely
```

Authentication is **separate from your app's session auth**. Admin login uses simple username/password credentials read from environment variables:

```env
ADMIN_USERNAME=admin
ADMIN_PASSWORD=your-secure-password
SECRET_KEY=<used for admin session encryption>
```

Visit <http://localhost:8000/admin>, enter those credentials, and you're in.

!!! warning "Login is disabled until credentials are configured"
    `ADMIN_USERNAME` and `ADMIN_PASSWORD` default to empty. With either unset, **every admin login attempt fails** — an empty form submission does not authenticate. Set both before the panel is usable.

## What You'll Learn

- **[Configuration](configuration.md)** - Environment variables and deployment settings
- **[Adding Models](adding-models.md)** - Register your own models with the admin interface
- **[User Management](user-management.md)** - Admin authentication and security

## What's Included

Each feature ships its own views, and `src/wiring/admin.py` lists the ones this
project registers. Out of the box that is two:

| View | Source | Notes |
|------|--------|-------|
| **Users** | `modules/user/admin.py` | Create / edit / delete users; password hashing applied automatically; soft-delete-aware; shows the tier column only when the tiers feature contributed one |
| **Tiers** | `modules/tier/admin.py` | Manage subscription tiers; lists and counts only live ones; uses `TierService.permanent_delete` to prevent orphaning users / rate limits |

Both are categorized under "Users & Access" and provide search, sort, filter, and CSV export.

If you want admin views for `RateLimit`, `APIKey`, etc., follow the [Adding Models](adding-models.md) guide.

## Common Operations

### Creating a User

Navigate to **Users → Create**. Fill the form. The `Password` field accepts plaintext — `UserAdmin.on_model_change` runs `get_password_hash()` before saving so the database only ever sees the hash.

### Editing a User

Click any user row → **Edit**. You can change the tier, toggle `is_superuser`, update OAuth fields, etc. The hashed password field is shown but you only need to fill it if you want to reset the password.

The tier picker lists only tiers a soft delete hasn't taken out, and a save that still names a
deleted one is refused with "That tier has been deleted. Pick another one."

### Deleting a Tier

The Tier delete button calls `TierService.permanent_delete`, which **fails** if any live user or
rate limit still references the tier. This prevents dangling foreign keys. Reassign or remove the
dependents first. Users a soft delete already removed are released from the tier as part of the
permanent delete; a *soft* delete of a tier (`DELETE /api/v1/tiers/{name}`) leaves them on it, so a
restore finds them where they were.

## How Authentication Works

The admin panel uses session-based auth via `SessionMiddleware` (Starlette), separate from the API's session system. When you submit the login form:

1. `AdminAuth.login` validates the credentials against `ADMIN_USERNAME` / `ADMIN_PASSWORD`
2. On success, sets `request.session["admin_authenticated"] = True`
3. Subsequent requests check that flag

This is intentionally simpler than the main app's session system — the admin panel is for a small number of trusted operators, not end users. The session is encrypted with `SECRET_KEY`.

## How It's Wired

The admin app is created in `src/interfaces/admin/initialize.py` and mounted in `src/interfaces/main.py` at startup:

```python
# interfaces/admin/initialize.py
from fastapi import FastAPI
from sqladmin import Admin

from ...infrastructure.config.settings import get_settings
from ...infrastructure.database.session import get_engine
from ...wiring.admin import ADMIN_VIEWS
from .auth import AdminAuth


def create_admin_interface(app: FastAPI) -> Admin | None:
    settings = get_settings()
    if not settings.ADMIN_ENABLED:
        return None

    admin = Admin(
        app=app,
        engine=get_engine(),
        authentication_backend=AdminAuth(secret_key=settings.SECRET_KEY),
        title="Admin",
    )
    for view in ADMIN_VIEWS:
        admin.add_view(view)
    return admin
```

The admin feature contributes `install(app)` to the wiring's installers, and the app
factory calls it, so nothing in `main.py` mentions the panel. If `ADMIN_ENABLED=false`,
nothing is mounted. The panel brings its own session middleware, scoped to its own
routes, so an API request never decodes an admin cookie.

## Disabling in Production

If you don't want the admin panel reachable in production, set:

```env
ADMIN_ENABLED=false
```

Or keep it enabled but restrict network access at the load balancer / proxy level (e.g. only allow `/admin` from your VPN's CIDR).

## Key Files

| Component | Location |
|-----------|----------|
| Admin app factory | `backend/src/interfaces/admin/initialize.py` |
| Authentication backend | `backend/src/interfaces/admin/auth.py` |
| Dataclass-model mixin | `backend/src/interfaces/admin/mixins.py` |
| User view | `backend/src/modules/user/admin.py` |
| Tier view | `backend/src/modules/tier/admin.py` |
| View registry | `backend/src/wiring/admin.py` |

## Next Steps

1. **[Configuration](configuration.md)** — Environment variables and deployment options
2. **[Adding Models](adding-models.md)** — Walkthrough for registering your own model views
3. **[User Management](user-management.md)** — Hardening the admin login for production
