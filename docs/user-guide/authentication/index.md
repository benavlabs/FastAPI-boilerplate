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
# → { "id": 1, "username": "admin", "csrf_token": "..." }

# Subsequent requests — send the cookie back
curl http://localhost:8000/api/v1/users/me -b cookies.txt

# Log out
curl -X POST http://localhost:8000/api/v1/auth/logout -b cookies.txt
```

Routes use `Depends(get_current_user)` to require an authenticated session.

### 2. OAuth (Google and GitHub)

For social sign-in — OAuth 2.0 with PKCE. The browser goes to the provider, signs in, and comes
back to a callback that creates the session and sends it on to your app.

```text
# Link or redirect the browser to (redirect_to is optional, same-origin paths only):
GET /api/v1/auth/oauth/google?redirect_to=/dashboard
# → 307 to https://accounts.google.com/...

# Google sends the browser back to:
GET /api/v1/auth/oauth/callback/google?code=...&state=...
# → session + CSRF cookies set, 307 to /dashboard (or to OAUTH_REDIRECT_BASE_URL)
```

GitHub works the same way, on `/api/v1/auth/oauth/github` and
`/api/v1/auth/oauth/callback/github`.

Register `{OAUTH_REDIRECT_BASE_URL}/api/v1/auth/oauth/callback/<provider>` as the redirect URI with
each provider — in the Google console, and as the "Authorization callback URL" of a GitHub OAuth app
(Settings → Developer settings → OAuth Apps → New OAuth App). `OAUTH_REDIRECT_BASE_URL` is the
public origin of the API, without a path. The paths above follow `API_PREFIX`, so a project that
moved the API registers the moved callback.

A failed sign-in - the user declined, or their address is longer than the `email` column - sends
the browser to `OAUTH_REDIRECT_BASE_URL?error=<code>`. A callback whose `state` doesn't match the
cookie set when the flow started, or whose state was already used or has expired, lands there too
with `error=invalid_state` and no session, since it may be a login-CSRF attempt; the usual cause is
a sign-in that took too long or finished in another browser, so offer to start again.
New accounts take their display name from the Google profile.

A provider is wired when **both** of its settings are set — `OAUTH_GOOGLE_CLIENT_ID` and
`OAUTH_GOOGLE_CLIENT_SECRET`, `OAUTH_GITHUB_CLIENT_ID` and `OAUTH_GITHUB_CLIENT_SECRET` — so a
project can run either, both, or neither, and a client id without its secret wires nothing. With no
provider configured the OAuth router isn't mounted at all.

GitHub reports its addresses separately (`GET /user/emails`), and crudauth's provider picks the
primary verified one. An address GitHub has not verified is refused:
`?error=email_unverified`, with no account created and no session — an unverified address must not
be able to claim one. GitHub accounts without a public name fall back to the login handle for the
display name.

The router is supplied by crudauth: PKCE, browser-bound single-use state, and safe same-origin
redirects. Add a further provider in `infrastructure/auth/setup.py` by listing its name in
`OAUTH_PROVIDERS` and giving it `OAUTH_<NAME>_CLIENT_ID` / `_CLIENT_SECRET` settings, as long as
crudauth registers a provider class under that name.

### 3. API Keys (Machine-to-Machine)

For server-to-server clients, programs, scripts, integrations:

```bash
# Create a key (requires an authenticated session)
curl -X POST "http://localhost:8000/api/v1/api-keys/" \
  -H "Content-Type: application/json" -H "X-CSRF-Token: <token>" \
  -b cookies.txt \
  -d '{"name": "Integration Key", "permissions": ["user.read"], "usage_limits": {}}'
# → { "api_key": "shown ONCE — store securely", "id": 1, "key_prefix": "...", ... }

# Call with it, in the X-API-Key header
curl http://localhost:8000/api/v1/auth/me -H "X-API-Key: fai_..."
# → { "user_id": 1, "username": "admin", ..., "via": "apikey" }
```

The full key is returned only on creation, in `api_key`. The rest of the response is what
`GET /api/v1/api-keys/{id}` reports, minus `key_metadata` and `last_used_ip`, which that route still
carries. Each key has its own scope ([registry permission names](permissions.md#api-key-scope)),
usage limits, and audit trail (`KeyUsage` rows).

A request carrying a valid key is authenticated as the key's owner, holding that owner's permissions
narrowed to the key's scope ([what a key holds](permissions.md#what-a-key-holds)), with
`transport="apikey"` on the principal and no CSRF token required: CSRF guards a cookie the browser attaches by itself, and a key
is sent deliberately. A key request is answered without a cookie, so it never becomes a session. A
key that is unknown, malformed, revoked, expired or whose owner a soft delete has taken out answers
`401`, including on a route that otherwise answers anonymous callers — a credential that is present
and wrong is not an absent one.

A session cookie wins when a request carries both, and these routes take **only** a session, so a
key cannot use itself to escalate or to hide its tracks:

| Route | Why |
|-------|-----|
| `POST /api/v1/auth/change-password` | an account changes its own password while signed in |
| `POST /api/v1/auth/email/change-request` | the same, for the address a recovery flow would use |
| `POST /api/v1/auth/logout`, `/logout-all` | a key holds no session to end |
| `GET /api/v1/auth/sessions`, `DELETE /api/v1/auth/sessions/{handle}` | a key holds no device to list or sign out |
| `DELETE /api/v1/users/{username}` | a key must not close the account that issued it |
| every `/api/v1/api-keys/` route | a key must not mint, read, rescope or revoke a key, its own included |

A password change revokes the account's other **sessions**; it does not revoke its keys, which carry
no password. Revoke a key that may have leaked with `DELETE /api/v1/api-keys/{id}`.

A key is stored as `sha256$<digest>` of itself: 256 bits from `secrets.token_urlsafe` need no salt
and no work factor, and a deterministic digest lets a request find its row by one indexed lookup. A
key an older version stored with a salted scrypt hash still authenticates, and its row is rewritten
as a digest the first time it does — until then, a request carrying that key's prefix still costs one
scrypt verification, so run the old keys once after upgrading.

## Recovery Flows (Email)

crudauth's recovery router is mounted under the same prefix, so the project ships email
verification, password reset and a confirmed email change:

```text
POST /api/v1/auth/email/verify-request    {"email": "..."}
POST /api/v1/auth/email/verify-confirm    {"token": "..."}
POST /api/v1/auth/password/reset-request  {"email": "..."}
POST /api/v1/auth/password/reset-confirm  {"token": "...", "new_password": "..."}
POST /api/v1/auth/email/change-request    {"new_email": "...", "password": "..."}   # authenticated
POST /api/v1/auth/email/change-confirm    {"token": "..."}
```

The `-request` routes answer the same whether or not the address belongs to an account, so they
can't be used to find out who has one, and they are rate limited per client address and per target
address. Delivery goes through the sender [`EMAIL_BACKEND`](../configuration/environment-variables.md#email)
names.

What crudauth guarantees, and this project's tests hold it to:

- A token is single-use, and dies early when the password, the address or `token_version` changes.
- A completed reset ends **every** session the account had, so a stolen one doesn't survive it.
- A confirmed email change notifies the **old** address (`email_changed`), which is how the previous
  owner finds out.
- An inactive account is sent nothing, and the links it already has stop working. `User.is_active`
  is `not is_deleted`, so a soft-deleted account is covered.

### Where the links point

The boilerplate serves no pages, so the links are built for **your** frontend:

```env
FRONTEND_URL=https://app.example.com
```

```text
{FRONTEND_URL}/verify-email?token=...
{FRONTEND_URL}/reset-password?token=...
{FRONTEND_URL}/confirm-email-change?token=...
```

Each page reads `token` from the query string and POSTs it to the matching `-confirm` route.
`FRONTEND_URL` is required in production: an empty or `localhost` value is refused at startup,
because every link built from it would be one nobody can open.

In development the default `console` backend logs the whole message, link included, so there is no
frontend to run — copy the token out of the log and confirm by hand:

```bash
curl -X POST http://localhost:8000/api/v1/auth/password/reset-request \
    -H "Content-Type: application/json" -d '{"email": "you@example.com"}'
# the API log prints: ... Subject: Reset your password
#                     ... http://localhost:3000/reset-password?token=eyJhbGciOi...

curl -X POST http://localhost:8000/api/v1/auth/password/reset-confirm \
    -H "Content-Type: application/json" \
    -d '{"token": "eyJhbGciOi...", "new_password": "An0therPassword!"}'
```

## Key Features

### Server-Side Sessions

- **Session storage**: Redis by default; the project's own database or memory available (`SESSION_BACKEND` env var)
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

- **Roles** carrying `resource.action` permissions (`modules/role/`) — `require_permissions("user.read")` gates a route, superusers bypass it
- **Superuser flag** on `User.is_superuser` for admin-only routes
- **Tier-based** access via the `Tier` model — every user belongs to a tier, and rate limits are configured per tier path
- **Resource ownership** checks live in services (the route doesn't decide who owns what)

### Login Lockout

`crudauth` throttles the login endpoint internally with an escalating per-IP / per-identifier lockout, whose thresholds are the `LOGIN_*` settings ([Authentication & Security](../configuration/environment-variables.md#authentication--security)). When the limit is hit, `POST /api/v1/auth/login` returns `429 Too Many Requests` with a `Retry-After` header telling the client how long to wait. Behind a reverse proxy, set `TRUSTED_PROXY_HOPS` so the lockout keys on the real client IP rather than the proxy's.

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

### Permission Required

```python
from ...infrastructure.auth.authorization import require_permissions

@router.get("/", dependencies=[require_permissions("user.read")])
async def get_users(
    db: AsyncSessionDep,
    user_service: UserServiceDep,
) -> dict[str, Any]:
    ...
```

Returns 403 unless the caller holds every named permission through one of their roles; superusers always pass. `infrastructure/auth/deps.py` exports `CurrentPermissionsDep` for handlers that need the permission set itself, and `CurrentPrincipalDep` for the crudauth `Principal`. See [Permissions](permissions.md#role-based-permissions).

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

- Insecure or placeholder `SECRET_KEY`
- Default or empty database password
- Admin panel enabled without `ADMIN_USERNAME`/`ADMIN_PASSWORD`
- `CORS_ORIGINS` containing `*`

An empty `CORS_ORIGINS` isn't an error: it means the app allows no cross-origin request. A `*`
is refused in production, and wherever it is allowed the app drops `CORS_ALLOW_CREDENTIALS`,
so cookies never travel to a wildcard origin.

## Configuration

The full reference is in [Environment Variables](../configuration/environment-variables.md). The most relevant settings:

```env
# Sessions
SESSION_TIMEOUT_MINUTES=30
SESSION_CLEANUP_INTERVAL_MINUTES=15
MAX_SESSIONS_PER_USER=5
SESSION_SECURE_COOKIES=true
SESSION_BACKEND=redis             # redis | database | memory

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
