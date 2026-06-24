# Authentication & Security

The boilerplate uses **server-side sessions with HTTP-only cookies** — not JWT. Auth is provided by the [`crudauth`](https://pypi.org/project/crudauth/) library: sessions are stored in Redis (or memory, configurable), CSRF-protected, and lockout-throttled at the login endpoint. The composition root is the `auth = CRUDAuth(...)` singleton in `infrastructure/auth/setup.py` (see [Sessions → Auth Architecture](sessions.md#auth-architecture)).

For machine-to-machine clients, the boilerplate ships **API keys** with per-key permissions and usage tracking.

## What You'll Learn

- **[Sessions](sessions.md)** - Server-side sessions, cookies, and CSRF protection
- **[User Management](user-management.md)** - Registration, login, profile operations
- **[Permissions](permissions.md)** - Role-based access control and resource ownership

## Why Sessions, Not JWT

The original boilerplate used JWT with refresh tokens and a token blacklist. We replaced that with sessions because:

- **Logout is trivial.** Delete the session row, done. No blacklist to maintain.
- **Rotating credentials is trivial.** Update the session record. No need to wait for tokens to expire.
- **CSRF is built in.** Server-side sessions naturally pair with double-submit CSRF tokens.
- **Storage is server-side.** No risk of accidentally leaking long-lived tokens via XSS to client storage.
- **Sessions match how most users actually want to think about authentication.** "Is this person logged in?" is a database question, not a cryptographic one.

If you specifically need stateless tokens (e.g. for inter-service auth where you can't share a session store), use **API keys** — they're stateless from the client's perspective and authenticated server-side.

### Need JWT for mobile or native apps?

Cookies and CSRF are awkward for mobile apps, native clients, and CLIs. crudauth handles this with a **bearer (JWT) transport** that runs *alongside* sessions — the boilerplate just doesn't enable it by default. Both transports resolve to the same `Principal`, so your route protection (`CurrentUserDep`, `get_current_user`, etc.) doesn't change; only how the client authenticates does.

To turn it on, add a `BearerTransport` to the `transports` list in `infrastructure/auth/setup.py` and mount crudauth's bearer router (which adds `POST /token` to log in and `POST /refresh` to mint a new access token):

```python
# infrastructure/auth/setup.py
from crudauth import BearerTransport, CookieConfig, CRUDAuth, SessionTransport

auth = CRUDAuth(
    session=async_session,
    user_model=User,
    SECRET_KEY=settings.SECRET_KEY,
    cookies=CookieConfig(secure=settings.SESSION_SECURE_COOKIES),
    transports=[
        SessionTransport(...),                       # browsers (unchanged)
        BearerTransport(access_ttl=900, refresh="body"),  # mobile / API clients
    ],
    ...
)
```

```python
# wherever the auth router is included (e.g. interfaces/api/v1)
app.include_router(auth.bearer_router, prefix="/api/v1/auth")
```

Mobile clients typically want `refresh="body"` so the refresh token comes back in the JSON response (to store themselves) rather than as a cookie. Clients then send the access token as `Authorization: Bearer <token>`. When both a session cookie and a bearer token are present, the **first transport in the list wins**.

For the full walkthrough — token lifecycle, refresh strategies, scopes, and running session + bearer together — see crudauth's [Bearer tokens](https://benavlabs.github.io/crudauth/guides/auth/bearer/) and [Multiple transports](https://benavlabs.github.io/crudauth/guides/auth/multiple-transports/) guides.

## Authentication Mechanisms

The boilerplate supports three auth pathways. They coexist; you pick the right one per endpoint.

### 1. Sessions (Browser Clients)

```bash
# Log in — server sets the session cookie and returns a CSRF token
curl -X POST "http://localhost:8000/api/v1/auth/login" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin&password=your_admin_password" \
  -c cookies.txt
# → { "csrf_token": "..." }

# Subsequent requests — send the cookie back
curl http://localhost:8000/api/v1/users/me -b cookies.txt

# Log out
curl -X POST http://localhost:8000/api/v1/auth/logout -b cookies.txt
```

Routes use `Depends(get_current_user)` to require an authenticated session.

### 2. OAuth (Google)

For social sign-in — Google OAuth 2.0 with PKCE is wired up. The user is redirected to Google, signs in, and is bounced back to a callback that creates a session.

```bash
# Start the flow
curl http://localhost:8000/api/v1/auth/oauth/google
# → { "url": "https://accounts.google.com/...?state=..." }

# After the user signs in at Google, they hit the callback:
# GET /api/v1/auth/oauth/callback/google?code=...&state=...
# The server creates a session and either redirects or returns JSON.
```

Only Google is wired (in the `oauth_providers` dict in `infrastructure/auth/oauth.py`), and the `User` model keeps `github_id` and `oauth_provider` columns. crudauth's `OAuthProviderFactory` already ships both `google` and `github` providers, so enabling **GitHub** is just adding a `"github"` entry to the `oauth_providers` dict and its two routes in `infrastructure/auth/routes.py` — no provider implementation needed. For a provider crudauth doesn't ship, register it with `OAuthProviderFactory` first, then wire the dict entry and routes the same way.

### 3. API Keys (Machine-to-Machine)

For server-to-server clients, programs, scripts, integrations:

```bash
# Create a key (requires an authenticated session)
curl -X POST "http://localhost:8000/api/v1/api-keys/" \
  -H "Content-Type: application/json" \
  -b cookies.txt \
  -d '{"name": "Integration Key", "permissions": {}, "usage_limits": {}}'
# → { "key": "shown ONCE — store securely", ... }
```

The full key is returned only on creation. Each key has its own permissions, usage limits, and audit trail (`KeyUsage` rows).

## Key Features

### Server-Side Sessions

- **Session storage**: Redis by default; memory available (`SESSION_BACKEND` env var)
- **HTTP-only cookies**: `session_id` cookie cannot be read by JavaScript
- **CSRF tokens**: Returned on login, also set as a cookie, must be sent in `X-CSRF-Token` for state-changing requests
- **Configurable timeout**: `SESSION_TIMEOUT_MINUTES`
- **Per-user limits**: `MAX_SESSIONS_PER_USER` caps simultaneous sessions per account
- **Automatic cleanup**: `SESSION_CLEANUP_INTERVAL_MINUTES` controls expiry sweeps

### User Management

- **Username or email** login (the same `/api/v1/auth/login` endpoint accepts either)
- **bcrypt** password hashing
- **Soft delete** for user records — accounts are deactivated, not destroyed (toggle via `is_deleted`)
- **GDPR/LGPD anonymization** endpoint for hard-clearing PII (`DELETE /api/v1/users/db/{username}`)
- **OAuth flag** on the user model (`google_id`, `github_id`, `oauth_provider`)

### Permission System

- **Superuser flag** on `User.is_superuser` for admin-only routes
- **Tier-based** access via the `Tier` model — every user belongs to a tier, and rate limits are configured per tier path
- **Resource ownership** checks live in services (the route doesn't decide who owns what)

### Login Lockout

`crudauth` throttles the login endpoint internally with an escalating per-IP / per-identifier lockout — there are no env vars to tune. When the limit is hit, `POST /api/v1/auth/login` returns `429 Too Many Requests` with a `Retry-After` header telling the client how long to wait. Behind a reverse proxy, set `TRUSTED_PROXY_HOPS` so the lockout keys on the real client IP rather than the proxy's.

## Authentication Patterns

All auth deps live in `src/infrastructure/auth/dependencies.py` (they wrap the `crudauth` `auth` singleton).

### Required Authentication

```python
from ...infrastructure.auth.dependencies import get_current_user

@router.get("/me", response_model=UserRead)
async def me(
    current_user: Annotated[dict[str, Any], Depends(get_current_user)],
) -> dict[str, Any]:
    return current_user
```

Returns 401 if the session cookie is missing or invalid.

### Optional Authentication

```python
from ...infrastructure.auth.dependencies import get_optional_user

@router.get("/")
async def list_things(
    user: Annotated[dict[str, Any] | None, Depends(get_optional_user)],
):
    # Logged-in users see extras; anonymous users still get a response
    if user is not None:
        return {"premium": True}
    return {"premium": False}
```

### Superuser Only

```python
from ...infrastructure.auth.dependencies import get_current_superuser

@router.delete("/{username}/permanent")
async def gdpr_delete_user(
    username: str,
    db: Annotated[AsyncSession, Depends(async_session)],
    user_service: Annotated[UserService, Depends(get_user_service)],
    _: Annotated[dict[str, Any], Depends(get_current_superuser)],
) -> dict[str, str]:
    ...
```

The leading underscore is the codebase's convention for dependency-only parameters.

### Resource Ownership

Ownership is checked in the service layer, not in the route:

```python
# modules/user/service.py
async def verify_user_permission(
    self,
    current_user: dict[str, Any],
    target_username: str,
    action: str,
) -> None:
    if current_user["username"] != target_username and not current_user["is_superuser"]:
        raise PermissionDeniedError(f"Cannot {action} for another user")
```

The route delegates and the service raises `PermissionDeniedError` (which auto-maps to 403). See [Exceptions](../api/exceptions.md) for the mapping layer.

## Security Features

### Session Security

- HTTP-only `session_id` cookie — JavaScript can't read it (XSS-safe)
- `Secure` cookies in non-dev environments (`SESSION_SECURE_COOKIES=true`)
- CSRF token validation for state-changing requests (`CSRF_ENABLED=true`)
- IP and user-agent recorded with each session
- Per-user session count cap (`MAX_SESSIONS_PER_USER`)

### Password Security

- bcrypt hashing with automatic salt
- Pydantic validation enforces minimum length and complexity at the schema level (`UserCreate.password`)
- Plaintext passwords are never stored or logged
- Login rate limiting prevents credential stuffing

### Production Validator

When `ENVIRONMENT=production` and `PRODUCTION_SECURITY_VALIDATION_ENABLED=true` (both default), the app refuses to start if it finds insecure settings:

- Default `SECRET_KEY` value
- `DEBUG=true`
- `CORS_ORIGINS=*`

`PRODUCTION_SECURITY_STRICT_MODE=true` makes the validator stricter still.

## Configuration

The full reference is in [Environment Variables](../configuration/environment-variables.md). The most relevant settings:

```env
# Sessions
SESSION_TIMEOUT_MINUTES=30
SESSION_CLEANUP_INTERVAL_MINUTES=15
MAX_SESSIONS_PER_USER=5
SESSION_SECURE_COOKIES=true
SESSION_BACKEND=redis             # redis | memory

# CSRF
CSRF_ENABLED=true                  # set false for dev/test

# Trusted reverse proxies in front of the app (real client IP for login lockout)
TRUSTED_PROXY_HOPS=0

# OAuth
OAUTH_REDIRECT_BASE_URL=http://localhost:8000
OAUTH_GOOGLE_CLIENT_ID=
OAUTH_GOOGLE_CLIENT_SECRET=
OAUTH_GITHUB_CLIENT_ID=            # data model anticipates GitHub; no provider/routes wired
OAUTH_GITHUB_CLIENT_SECRET=

# Security
SECRET_KEY=<openssl rand -hex 32>
PRODUCTION_SECURITY_VALIDATION_ENABLED=true
PRODUCTION_SECURITY_STRICT_MODE=false
```

## Quick Examples

### Frontend Login Flow (JavaScript)

```javascript
class AuthClient {
    async login(username, password) {
        const res = await fetch('/api/v1/auth/login', {
            method: 'POST',
            credentials: 'include',                   // important — accept cookies
            headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
            body: new URLSearchParams({ username, password }),
        });
        if (!res.ok) throw new Error('login failed');
        const { csrf_token } = await res.json();
        // Store the CSRF token in memory; cookie is set automatically
        this.csrfToken = csrf_token;
        return csrf_token;
    }

    async post(url, body) {
        return fetch(url, {
            method: 'POST',
            credentials: 'include',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRF-Token': this.csrfToken,       // required for state-changing requests
            },
            body: JSON.stringify(body),
        });
    }

    async logout() {
        await fetch('/api/v1/auth/logout', {
            method: 'POST',
            credentials: 'include',
            headers: { 'X-CSRF-Token': this.csrfToken },
        });
        this.csrfToken = null;
    }
}
```

The `credentials: 'include'` flag is what makes the browser actually send cookies cross-origin. Pair this with proper CORS settings on the server side (`CORS_ALLOW_CREDENTIALS=true`).

### Custom Tier-Based Dependency

You can combine the built-in deps to enforce tier checks:

```python
from typing import Annotated, Any
from fastapi import Depends, HTTPException

from ...infrastructure.auth.dependencies import get_current_user


async def require_tier(
    tier_name: str,
    user: Annotated[dict[str, Any], Depends(get_current_user)],
) -> dict[str, Any]:
    user_tier = user.get("tier") or {}
    if user_tier.get("name") != tier_name:
        raise HTTPException(status_code=403, detail=f"Requires {tier_name} tier")
    return user


# Usage with a Pro tier
@router.get("/premium")
async def premium_feature(
    user: Annotated[dict[str, Any], Depends(lambda u=Depends(get_current_user): require_tier("pro", u))],
):
    return {"data": "premium content"}
```

In practice, prefer raising `PermissionDeniedError` from inside a service method so the mapping layer translates it consistently (see [Exceptions](../api/exceptions.md)).

## Getting Started

1. **[Sessions](sessions.md)** — How sessions work, cookie handling, CSRF
2. **[User Management](user-management.md)** — Registration, login, profile
3. **[Permissions](permissions.md)** — Role-based and resource-based access control

## What's Next

- **[Environment Variables](../configuration/environment-variables.md)** — All auth-related settings
- **[Exceptions](../api/exceptions.md)** — How `PermissionDeniedError` and friends become HTTP 403/401
- **[API Endpoints](../api/endpoints.md)** — Patterns for protecting routes
