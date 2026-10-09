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
project registers. Out of the box that is five:

| View | Source | Notes |
|------|--------|-------|
| **Users** | `modules/user/admin.py` | Create / edit / delete users; password hashing applied automatically; soft-delete-aware; shows the tier column only when the tiers feature contributed one |
| **Tiers** | `modules/tier/admin.py` | Manage subscription tiers; lists and counts only live ones; uses `TierService.permanent_delete` to prevent orphaning users / rate limits |
| **Roles** | `modules/role/admin.py` | Create / rename / delete roles; the listing shows the permissions each one carries |
| **Role permissions** | `modules/role/admin.py` | One grant per row; the permission field is a picker over the registry |
| **User roles** | `modules/role/admin.py` | Who holds which role; the listing, its count and the account picker all leave out accounts a soft delete has taken out |

All five are categorized under "Users & Access"; Users and Tiers provide search, sort, filter, and
CSV export. The three role views come with the rbac feature, and each view with the feature that
owns its table, so a project without one of them registers fewer.

If you want admin views for `RateLimit`, `APIKey`, etc., follow the [Adding Models](adding-models.md) guide.

## Common Operations

### Creating a User

Navigate to **Users → Create**. Fill the form. The `Password` field accepts plaintext — `UserAdmin.on_model_change` runs `get_password_hash()` before saving so the database only ever sees the hash.

### Editing a User

Click any user row → **Edit**. You can change the name, username, email, the tier, the OAuth identifiers and `is_superuser`. The edit form has no password field (`form_edit_rules` comes from `UserAdminUpdate`), so a reset goes through the API's change-password route or a new hash written directly.

The tier picker lists only tiers a soft delete hasn't taken out, and a save that still names a
deleted one is refused with "That tier has been deleted. Pick another one."

### Giving an Account a Role

A role is built in two places: **Roles → Create** names it, and **Role permissions → Create** adds
one permission to it per row. The permission field offers only names the registry knows, and a write
that goes around the form is refused by the model as well, so a grant the project could never check
cannot be stored. A grant and a holding are a pair of rows with nothing else to edit, so both views
create and delete rather than edit: to change a role's permissions, delete the grant and add
another.

**User roles → Create** hands a role to an account. The listing, the total it paginates by and the
account picker all leave out accounts a soft delete has taken out — they are nobody to hand a role
to — while the API's `GET /api/v1/users/{user_id}/roles` still reads what such an account held.

!!! warning "The panel is above the delegation checks"
    The API refuses to grant a permission, or to touch an account, stronger than the caller
    ([Permissions](../authentication/permissions.md#managing-roles)). The panel has no such caller:
    it signs in with `ADMIN_USERNAME` / `ADMIN_PASSWORD`, and those credentials already let it set
    `is_superuser` on any user, so there is no weaker operator to hold back. Whoever can reach
    `/admin` can grant anything the registry knows.

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

This is intentionally simpler than the main app's session system — the admin panel is for a small number of trusted operators, not end users. The session cookie is signed with `SECRET_KEY`, not encrypted: its contents are readable by whoever holds it, and the signature is what stops it being forged. Its `Path` is the panel's own mount — `ADMIN_BASE_URL`, with any `root_path` the request arrived through — so the API never receives it, and an API route can never be reached with an operator's panel session.

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
| Role, grant and holder views | `backend/src/modules/role/admin.py` |
| View registry | `backend/src/wiring/admin.py` |

## Next Steps

1. **[Configuration](configuration.md)** — Environment variables and deployment options
2. **[Adding Models](adding-models.md)** — Walkthrough for registering your own model views
3. **[User Management](user-management.md)** — Hardening the admin login for production
