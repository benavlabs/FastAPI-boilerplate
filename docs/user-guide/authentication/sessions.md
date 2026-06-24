# Sessions

Sessions are the boilerplate's default authentication mechanism. All built-in API routes use session auth.

## Auth Architecture

Authentication is provided by the [`crudauth`](https://pypi.org/project/crudauth/) library. The composition root is a single singleton in `infrastructure/auth/setup.py`:

```python
# infrastructure/auth/setup.py
auth = CRUDAuth(session=async_session, user_model=User, SECRET_KEY=settings.SECRET_KEY, ...)
```

Routers and dependencies reference `auth` at import time, and the app lifespan calls `auth.initialize()` on startup and `auth.shutdown()` on teardown (wired in `app_factory`) to open and close the session backend connections. Everything below — the dependencies, login flow, CSRF, lockout, and session storage — is this singleton in action; the boilerplate only supplies the wiring and route handlers.

## Protecting Routes

Import the session dependencies and add them to your routes:

```python
from typing import Annotated, Any
from fastapi import APIRouter, Depends

from ...infrastructure.auth.dependencies import get_current_user

router = APIRouter()


@router.get("/my-profile")
async def get_profile(
    current_user: Annotated[dict[str, Any], Depends(get_current_user)],
) -> dict[str, Any]:
    return {"user_id": current_user["id"], "email": current_user["email"]}
```

If the request doesn't have a valid session, the boilerplate returns `401 Unauthorized`.

### Available Dependencies

All from `src/infrastructure/auth/dependencies.py`. They wrap the `crudauth` `auth` singleton, so cookie validation, CSRF, and login lockout live in the library while your handlers keep working with plain user dicts.

**`get_current_user`** — Returns the authenticated user dict. Raises 401 if not authenticated.

```python
@router.get("/dashboard")
async def dashboard(
    current_user: Annotated[dict[str, Any], Depends(get_current_user)],
) -> dict[str, Any]:
    return {"welcome": current_user["username"]}
```

**`get_current_superuser`** — Same as `get_current_user`, plus checks `is_superuser=True`. Raises 403 if not a superuser.

```python
@router.delete("/users/{user_id}")
async def delete_user(
    user_id: int,
    current_user: Annotated[dict[str, Any], Depends(get_current_superuser)],
) -> None:
    # Only superusers reach this code
    ...
```

**`get_optional_user`** — Returns the user dict if authenticated, `None` otherwise. Never raises.

```python
@router.get("/products")
async def list_products(
    current_user: Annotated[dict[str, Any] | None, Depends(get_optional_user)],
) -> list[dict[str, Any]]:
    if current_user:
        # Personalize for logged-in users
        ...
```

**`get_current_principal`** — Returns the crudauth `Principal` (session-validated, CSRF-enforced). Use it when you need the session id (`principal.metadata["session_id"]`) or the `user_id` directly rather than the full user dict. `get_optional_principal` is the never-raises variant.

### Protecting Entire Routers

Apply auth to every route in a router:

```python
router = APIRouter(
    prefix="/admin",
    dependencies=[Depends(get_current_superuser)],
)


@router.get("/stats")
async def stats() -> dict[str, Any]:
    # Already authenticated at the router level
    ...
```

Note: router-level dependencies don't inject values into handlers. If you need the user object inside the handler, also add `Depends(get_current_user)` to that specific route.

## How Sessions Work

The login route delegates to the `crudauth` `auth` singleton (see [Auth Architecture](#auth-architecture)). When a user hits `POST /api/v1/auth/login`, crudauth:

1. Applies its per-IP / per-identifier login lockout (returns `429` + `Retry-After` if tripped)
2. Validates the credentials against the user row (soft-deleted users — `is_active == False` — are rejected)
3. Writes a session record to the configured backend (Redis by default)
4. Generates a CSRF token bound to the session
5. Sets two cookies on the response:
    - `session_id` — HTTP-only, the session identifier
    - `csrf_token` — readable by JS, mirrors the CSRF token returned in the JSON body

On every subsequent request, the auth dependency (via crudauth):

1. Reads `session_id` from cookies
2. Looks it up in the configured backend; rejects expired or missing sessions
3. For mutating requests (POST/PUT/DELETE/PATCH), validates the CSRF token if `CSRF_ENABLED=true`
4. Hands back a `Principal`; `get_current_user` then re-loads the full user row (joined with the `Tier` relationship via `lazy="selectin"`)

Logout (`POST /api/v1/auth/logout`) terminates the session record and clears the cookies.

## CSRF Protection

Session auth ships with CSRF protection. For non-GET requests, send the CSRF token via either:

- The `csrf_token` cookie (browsers send it automatically), or
- The `X-CSRF-Token` header (typical for JS clients)

```javascript
const csrfToken = getCookie('csrf_token');

await fetch('/api/v1/users/', {
    method: 'POST',
    credentials: 'include',          // include cookies cross-origin
    headers: {
        'X-CSRF-Token': csrfToken,
        'Content-Type': 'application/json',
    },
    body: JSON.stringify(data),
});
```

Need a fresh token mid-session? Hit `POST /api/v1/auth/refresh-csrf` — it returns a new token and sets the cookie.

For dev/test environments where CSRF gets in the way, set `CSRF_ENABLED=false`.

## Device Tracking

`crudauth` records session metadata (IP address, User-Agent, timestamps) internally as part of each session record. The boilerplate does **not** surface a device-listing route or a `SessionData` schema — that metadata lives inside the library's session store. If you need an "active sessions" UI, build it on crudauth's session APIs (`auth.sessions`) rather than expecting a ready-made dependency here.

## Login Lockout

Failed login attempts are throttled by `crudauth` itself. It applies an **escalating per-IP / per-identifier lockout** and, once tripped, returns `429 Too Many Requests` with a `Retry-After` header on `/api/v1/auth/login`. This happens automatically inside the login flow — there's nothing to wire up and no env vars to tune. Behind a reverse proxy, set `TRUSTED_PROXY_HOPS` so the lockout keys on the real client IP rather than the proxy's.

## Session Limits

Per-user concurrent session count is capped by `MAX_SESSIONS_PER_USER` (default 5). When a user logs in beyond this cap, the oldest session is terminated.

## Storage Backends

Sessions are stored server-side. Configure via `SESSION_BACKEND`:

| Value | When to use |
|-------|-------------|
| `redis` *(default)* | Production. Supports key expiration, pattern scans for cleanup, persists across restarts |
| `memory` | Tests only. Cleared on restart, not safe for multi-process deploys |

The backends ship inside the `crudauth` library, not the boilerplate — `setup.py` just selects `redis` or `memory` based on `SESSION_BACKEND`. (Memcached is no longer a session option; it remains available for the general cache and rate limiter.)

## Configuration

```env
# Backend
SESSION_BACKEND=redis                # redis | memory

# Lifetime
SESSION_TIMEOUT_MINUTES=30           # inactive sessions expire
SESSION_CLEANUP_INTERVAL_MINUTES=15  # how often the storage backend sweeps expired entries

# Per-user cap
MAX_SESSIONS_PER_USER=5

# Cookie security (HTTPS only)
SESSION_SECURE_COOKIES=true

# CSRF
CSRF_ENABLED=true

# Trusted reverse proxies in front of the app (real client IP for login lockout)
TRUSTED_PROXY_HOPS=0
```

For development you'll typically set `SESSION_SECURE_COOKIES=false` and `CSRF_ENABLED=false` so cookies work over plain HTTP and curl/Postman aren't blocked. Re-enable both for staging and production.

## Login & Logout Flow

### Login

```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin&password=your_admin_password" \
  -c cookies.txt
```

Response:

```json
{ "csrf_token": "..." }
```

The HTTP-only `session_id` cookie is now in `cookies.txt`. The CSRF token is also set as a cookie *and* returned in the body so JS clients can store it (browsers can't read HTTP-only cookies).

### Authenticated Request

```bash
curl http://localhost:8000/api/v1/users/me -b cookies.txt
```

For mutating requests, add the CSRF header:

```bash
curl -X POST http://localhost:8000/api/v1/users/ \
  -b cookies.txt \
  -H "Content-Type: application/json" \
  -H "X-CSRF-Token: <token-from-login-response>" \
  -d '{"name": "...", "username": "...", "email": "...", "password": "..."}'
```

### Refresh CSRF Token

```bash
curl -X POST http://localhost:8000/api/v1/auth/refresh-csrf -b cookies.txt
```

### Logout

```bash
curl -X POST http://localhost:8000/api/v1/auth/logout -b cookies.txt
```

Terminates the session and clears the cookies.

## Key Files

| Component | Location |
|-----------|----------|
| `auth = CRUDAuth(...)` singleton | `backend/src/infrastructure/auth/setup.py` |
| Dependencies | `backend/src/infrastructure/auth/dependencies.py` |
| OAuth building blocks | `backend/src/infrastructure/auth/oauth.py` |
| Login/logout/OAuth routes | `backend/src/infrastructure/auth/routes.py` |
| HTTP exceptions (fastcrud re-export) | `backend/src/infrastructure/auth/http_exceptions.py` |
| Auth settings | `backend/src/infrastructure/config/settings.py` (`AuthSettings`) |

Session storage, CSRF, and lockout themselves live in the `crudauth` library, not the boilerplate.

---

[← Authentication Overview](index.md){ .md-button } [User Management →](user-management.md){ .md-button .md-button--primary }
