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

**`get_current_permissions`** — Returns the permissions the caller effectively holds through the roles assigned to them, as a `frozenset[str]`. FastAPI caches it for the length of the request, so the lookup runs once however many guards ask for it. Superusers hold every registered permission.

```python
@router.patch("/{username}")
async def update_user_profile(
    username: str,
    permissions: Annotated[frozenset[str], Depends(get_current_permissions)],
) -> dict[str, str]:
    if "user.update" in permissions:
        ...
```

**`require_permissions(*names)`** — Returns a dependency that raises 403 unless the caller holds every named permission. Superusers pass. It injects nothing, so it goes in the route's `dependencies`:

```python
from ...infrastructure.auth.authorization import require_permissions


@router.get("/", dependencies=[require_permissions("user.read")])
async def get_users(...) -> dict[str, Any]:
    ...
```

See [Permissions](permissions.md#role-based-permissions) for declaring the names these take.

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
3. Writes a session record to the configured backend (Redis by default), under an HMAC of the
   session id rather than the id itself
4. Generates a CSRF token bound to the session
5. Sets two cookies on the response:
    - `session_id` — HTTP-only, the session identifier
    - `csrf_token` — readable by JS, mirrors the CSRF token returned in the JSON body

On every subsequent request, the auth dependency (via crudauth):

1. Reads `session_id` from cookies
2. Looks it up in the configured backend, by that same HMAC; rejects expired or missing sessions
3. For mutating requests (POST/PUT/DELETE/PATCH), validates the CSRF token if `CSRF_ENABLED=true`
4. Hands back a `Principal`; `get_current_user` then re-loads the full user row (joined with the `Tier` relationship via `lazy="selectin"`)

Signing in again ends the session the browser presented, so a cookie somebody copied stops working
at the account's next login.

The store never holds a session id or a CSRF token: each is kept under an HMAC keyed with
`SECRET_KEY`. Read access to the store yields nothing anybody can sign in with, and changing
`SECRET_KEY` signs everyone out.

crudauth's session-management routes are mounted beside the project's own: `GET /sessions`,
`DELETE /sessions/{handle}`, `POST /logout-all` and `POST /csrf/refresh` — see
[Manage Devices](#manage-devices).

Logout (`POST /api/v1/auth/logout`) hands the request to the session transport's
`complete_logout`, which terminates the session record, clears the cookies of every configured
transport and runs the `on_after_logout` hook with the ended session's handle — so an audit log
registered through `AuthHooks` sees a logout the same way it sees a login. To end every session the
user holds on all devices (e.g. after a suspected compromise), use `POST /api/v1/auth/logout-all`.
See [Logout All Sessions](#logout-all-sessions).

### Two timeouts

`SESSION_TIMEOUT_MINUTES` is an idle timeout: every authenticated request slides it forward, so a
session in use never ends on its own. `SESSION_ABSOLUTE_TIMEOUT_HOURS` caps a session from sign-in
however active it stays, for a project that wants a periodic re-login. It is unset by default, which
leaves the idle timeout as the only one; a value below 1 is refused at startup rather than expiring
every session the moment it is created. A session past the cap is removed, not just rejected, and
the next request answers `401`.

### Asking for a fresh sign-in

Some actions want proof that whoever holds the cookie is still at the keyboard. Set
`FRESH_SIGN_IN_SECONDS` and the routes that ask for one refuse a session that signed in longer ago
than that, with `403 Sign in again to continue.`; the client sends the user back through
`/api/v1/auth/login` and retries. Only a session can be fresh, so an API key or any other
credential never is.

Unset, closing an account asks nothing, while crudauth's own `/set-password` and MFA-enrolment
routes — where a project mounts them; this one mounts neither — keep crudauth's 10-minute default.
Setting it applies one window to all of them.

`DELETE /api/v1/users/{username}`, closing an account, is the route this project gates on it. To ask
it of one of your own, take `FreshSessionPrincipalDep` instead of `SessionPrincipalDep`:

```python
from src.infrastructure.auth.deps import FreshSessionPrincipalDep


@router.post("/billing/close")
async def close_billing(principal: FreshSessionPrincipalDep) -> dict[str, str]: ...
```

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

Need a fresh token mid-session? Hit `POST /api/v1/auth/csrf/refresh` — it returns the session's token, minting a new one only when the old is gone or expired, and sets the cookie.

## Passwords

crudauth's account routes are mounted under `/api/v1/auth`:

| Route | What it does |
|---|---|
| `POST /api/v1/auth/change-password` | Verifies `current_password`, sets `new_password`, bumps `token_version` and revokes the account's **other** sessions, keeping the current one. At most 5 calls per hour per account, successes included |
| `GET /api/v1/auth/me` | The identity crudauth resolved: id, username, email, superuser, scopes, transport |

```bash
curl -X POST http://localhost:8000/api/v1/auth/change-password \
  -b cookies.txt \
  -H "Content-Type: application/json" \
  -H "X-CSRF-Token: <token>" \
  -d '{"current_password": "<current>", "new_password": "<new>"}'
```

A wrong `current_password` answers `401`, a missing `X-CSRF-Token` answers `403`, and a
`new_password` that breaks the policy answers `422`. This route and the email change on
is capped at 5 per hour per account. Every call that checks a password counts, whether the password
was right or wrong; past that the route answers `429`.

crudauth also ships `POST /set-password`, for an account that has no password. This app does **not**
mount it: it would let anyone holding a session put a password on a provider-only account, which is
a takeover whenever a session is borrowed. An account that signs in with a provider sets its first
password the same way anyone recovers a forgotten one — through the reset link, which proves the
address before it accepts a new password:

```bash
curl -X POST http://localhost:8000/api/v1/auth/password/reset-request \
  -H "Content-Type: application/json" -d '{"email": "you@example.com"}'
# then POST the token from the link to /api/v1/auth/password/reset-confirm
```

After that the account can sign in with either the provider or its password. See
[Recovery Flows](index.md#recovery-flows-email).

Hashes another system wrote are accepted at login through `legacy_verifiers`, and replaced with
crudauth's own as each owner signs in once — see [Migrating Passwords](migrating-passwords.md).

For dev/test environments where CSRF gets in the way, set `CSRF_ENABLED=false`.

## Device Tracking

`crudauth` records session metadata (IP address, User-Agent, timestamps) internally as part of each session record. The boilerplate does **not** surface a device-listing route or a `SessionData` schema — that metadata lives inside the library's session store. If you need an "active sessions" UI, build it on crudauth's session APIs (`auth.sessions`) rather than expecting a ready-made dependency here.

## Login Lockout

Failed login attempts are throttled by `crudauth` itself. It applies an **escalating per-IP / per-identifier lockout** and, once tripped, returns `429 Too Many Requests` with a `Retry-After` header on `/api/v1/auth/login`. The thresholds are four settings, passed to crudauth as a `LockoutConfig` in `infrastructure/auth/setup.py`:

```env
LOGIN_MAX_ATTEMPTS=5             # failures allowed inside the window, per address and per account
LOGIN_ATTEMPT_WINDOW_SECONDS=900 # how long failures keep counting
LOGIN_LOCKOUT_BASE_SECONDS=300   # first lockout, doubling each round
LOGIN_LOCKOUT_MAX_SECONDS=3600   # ceiling for the doubling
```

The window is the value that matters against a paced attack: crudauth's own default counts over 60 seconds, so five tries a minute never accumulate. A successful login clears the account's failures and the pressure its own failures put on that address. The admin panel counts on this same policy, so an address guessing passwords is slowed at both doors. Behind a reverse proxy, set `TRUSTED_PROXY_HOPS` so the lockout keys on the real client IP rather than the proxy's.

With `RATE_LIMITER_BACKEND=redis`, the counters live in Redis, and crudauth builds the lockout policy with `fail_open=False`. If that Redis is unreachable, **every login is refused** with `429` for the base lockout window rather than let through unchecked: an attacker can't disable the lockout by taking Redis down. Treat the limiter's Redis as a dependency logins need, and watch it: `GET /health/ready` answers `503` while it is unreachable, and the log names it (`rate_limiter`), alongside the database and the session store. It is its own connection (`RATE_LIMITER_REDIS_*`, against `CACHE_REDIS_*` for the cache), and the readiness probe asks each server once even when several settings point at the same one. `RATE_LIMITER_BACKEND=memory` keeps the counters in the process instead, which is fine for a single worker and useless across several. `RATE_LIMITER_BACKEND=database` keeps them in `crudauth_counters`, shared by every worker; the database's own readiness check then covers them, and the `rate_limiter` check reports nothing to reach.

### What a refusal records

Every refused password login writes one `WARNING` on the `src.infrastructure.auth.audit` logger,
through crudauth's `on_login_failed` and `on_lockout` hooks:

```
login refused: 'ada' from 203.0.113.7 (curl/8.4.0); invalid_credentials
login refused: an identifier no account has from 203.0.113.7 (curl/8.4.0); invalid_credentials
login locked out for 300s, from 203.0.113.7 (curl/8.4.0)
```

The reason is `invalid_credentials` or `inactive`, which the response does not distinguish — a
disabled account and a wrong password are both `401`, and the log is where they are told apart. The
address is the one `TRUSTED_PROXY_HOPS` resolves, so it is the client's rather than a proxy's.

**An identifier is written out only where an account has it.** What arrives in the username field
may be a typo, a probe, someone else's address or a password typed one box too high, so a refusal
that resolved no account records only that, with the address and user agent an attack is recognised
by. The lockout line names no identifier at all: it refuses the request before anything resolves
one, and every attempt that filled the budget was already recorded.

Both hooks run after the refusal is decided and cannot change it; an exception either one raises is
logged by crudauth and the request answers normally. `infrastructure/auth/audit.py` is where a
project sends these to an audit table or an external sink instead.

## Running a second crudauth app beside this one

Two apps that each run crudauth — this API and another service, or a separate admin application —
share whatever storage they point at. Nothing in crudauth namespaces itself per app, so the two
collide wherever they meet:

| What they share | What happens | How to separate them |
|---|---|---|
| The session and CSRF key space on one Redis database | The per-user index is keyed by user id, not by an HMAC, so each app's device list, `logout-all` and session cap reach the other's sessions for the same id, even if the ids name different people. With the same `SECRET_KEY`, a session cookie from one app also signs in to the other | A different `SESSION_REDIS_DB` (or `SESSION_REDIS_URL`), or `SessionTransport(storage_prefix="other:session:", csrf_storage_prefix="other:csrf:")` |
| Cookie names in one browser | crudauth's cookies are `session_id` and `csrf_token` on path `/`, so the second login overwrites the first and the two apps sign each other out | `SessionTransport(cookie_name="other_session", csrf_cookie_name="other_csrf")` — the two names must differ from each other, which crudauth enforces |
| Login lockout and throttle counters | A username or address locked out in one app is locked out of the other, and the two apps' failures add up | A different `RATE_LIMITER_REDIS_DB`, or a key prefix (below) |
| `crudauth_store` / `crudauth_counters` in one database | The same collisions in rows rather than keys: the store indexes sessions by a `user_id` column, and the counters share their names | Separate databases or schemas, or the same prefixes: `storage_prefix` and the limiter's |

The tidiest separation in this project is the one it already uses between its own concerns: give the
other app its own Redis database. The cache sits on `0`, the rate limiter on `1`, sessions on `2`
and taskiq on `3`, so a second app starts at `4` and shares nothing.

Where they must share one database, prefix everything:

```python
# the other app's setup.py — not this one's
auth = CRUDAuth(
    ...,
    transports=[
        SessionTransport(
            cookie_name="other_session",
            csrf_cookie_name="other_csrf",
            storage_prefix="other:session:",
            csrf_storage_prefix="other:csrf:",
        )
    ],
    rate_limit_prefix="other:rl:",
)
```

`rate_limit_prefix` applies to the limiter crudauth builds for itself, and crudauth refuses it
together with `rate_limiter=`. This project passes its own limiter (`build_rate_limiter()` in
`infrastructure/auth/limiter.py`), so the prefix belongs there instead —
`redis_rate_limiter(client=..., prefix="other:rl:")`, or `database_store.rate_limiter(prefix=...)`
on the database backend.

The one-time-token, OAuth-state and MFA stores are keyed by values the server generates at random,
so sharing their key space is harmless; a signed token from one app is refused by the other anyway
unless both hold the same `SECRET_KEY`.

!!! note "The admin panel is not one of these"
    The panel this boilerplate ships is [sqladmin](../admin-panel/index.md), not a second crudauth
    app. It authenticates against `ADMIN_USERNAME` / `ADMIN_PASSWORD` with a Starlette cookie of its
    own — `admin_session`, signed with `SECRET_KEY` and scoped to the panel's mount — and it counts
    its login failures in a lockout of its own, against the identifier `admin-panel:<address>`,
    under a key prefix of its own. So one address has separate budgets at the two doors, and nothing
    submitted to `/api/v1/auth/login` can lock the panel out; the cost is that an address already
    failing at the API's door arrives at the panel unslowed. None of the prefixes above apply to it.

## Session Limits

Per-user concurrent session count is capped by `MAX_SESSIONS_PER_USER` (default 5). When a user logs in beyond this cap, the oldest session is terminated.

## Storage Backends

Sessions are stored server-side. Configure via `SESSION_BACKEND`:

| Value | When to use |
|-------|-------------|
| `redis` *(default)* | Production. Supports key expiration, pattern scans for cleanup, persists across restarts |
| `memory` | Tests only. Cleared on restart, not safe for multi-process deploys |

The backends ship inside the `crudauth` library, not the boilerplate — `setup.py` just selects `redis`, `database` or `memory` based on `SESSION_BACKEND`, and a value it has no store for is refused when the app starts. (Memcached is no longer a session option; it remains available for the general cache and rate limiter.)

`database` keeps sessions, CSRF tokens, the one-time tokens behind the email flows and the OAuth
state in two tables of this project's own database — `crudauth_store` and `crudauth_counters` —
so several workers share them with no Redis to run. The tables are declared on the project's
`Base.metadata`, so `alembic revision --autogenerate` writes them beside your own and
`CREATE_TABLES_ON_STARTUP` creates them in development: switching to or from `database` is a
schema change, and wants one migration. Expired rows are deleted as the store writes, and
`DatabaseStore.purge_expired()` clears them all if you would rather run that on a schedule.

## Configuration

```env
# Backend
SESSION_BACKEND=redis                # redis | database | memory
SESSION_REDIS_DB=2                   # on the cache Redis; isolated from cache (0), rate limiter (1), and taskiq (3)
# SESSION_REDIS_URL=                 # optional dedicated session Redis, e.g. rediss://user:password@host:6380/0

# Lifetime
SESSION_TIMEOUT_MINUTES=30           # inactive sessions expire
# SESSION_ABSOLUTE_TIMEOUT_HOURS=12  # the most a session may live from sign-in; unset for no cap
# FRESH_SIGN_IN_SECONDS=600            # how recent a sign-in must be for the routes that ask; unset, closing an account asks nothing
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
{ "id": 1, "username": "admin", "csrf_token": "..." }
```

The HTTP-only `session_id` cookie is now in `cookies.txt`. The CSRF token is also set as a cookie *and* returned in the body so JS clients can store it (browsers can't read HTTP-only cookies).

Add `remember_me=true` to the form to make the session cookie persistent; without it the cookie ends
with the browser session. A login the browser marks `Sec-Fetch-Site: cross-site` is refused with
`403`, so another site can't sign a visitor into an account it controls. Clients that don't send the
header, such as `curl` or a mobile app, are unaffected.

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
curl -X POST http://localhost:8000/api/v1/auth/csrf/refresh -b cookies.txt
```

It self-heals: a token that is still valid comes back unchanged, so a client that calls it on every
page load doesn't rotate a healthy one. Rate limited per address (crudauth's `csrf_refresh` default:
30 per hour).

### Logout

```bash
curl -X POST http://localhost:8000/api/v1/auth/logout -b cookies.txt
```

Terminates the session and clears the cookies.

### Logout All Sessions

```bash
curl -X POST http://localhost:8000/api/v1/auth/logout-all \
  -b cookies.txt \
  -H "X-CSRF-Token: <token-from-login-response>"
```

Terminates **every** session for the current user across all devices, including this one, and clears the cookies:

```json
{ "detail": "Signed out of all sessions.", "revoked": 3 }
```

To sign out only the *other* devices and stay logged in here, pass `keep_current=true`:

```bash
curl -X POST "http://localhost:8000/api/v1/auth/logout-all?keep_current=true" \
  -b cookies.txt \
  -H "X-CSRF-Token: <token-from-login-response>"
```

No re-authentication step is required, because this is the action a user needs when they can't trust their current session. It's rate limited per user (crudauth's `logout_all` default: 10 per hour).

### Manage Devices

```bash
curl http://localhost:8000/api/v1/auth/sessions -b cookies.txt
```

```json
[
  {"id": "7f3c…", "device": "Chrome on macOS", "ip": "203.0.113.7",
   "created_at": "2026-10-08T09:12:44Z", "last_activity": "2026-10-08T11:03:02Z", "current": true}
]
```

Every session the account holds, with the caller's flagged `current`. `id` is the session's
*handle*, never its id, so the listing is safe to render in a page: nothing in it authenticates.
Sign one device out with it:

```bash
curl -X DELETE http://localhost:8000/api/v1/auth/sessions/7f3c… \
  -b cookies.txt \
  -H "X-CSRF-Token: <token-from-login-response>"
```

Ownership is checked, and a handle that belongs to somebody else answers `404` — the same as one
that doesn't exist, so the route reveals nothing. Revoking the caller's own handle clears its
cookies. Every session backend this project offers can list a user's sessions: memory scans its
entries, Redis keeps a per-user index, and the database store has a `user_id` column.

## Key Files

| Component | Location |
|-----------|----------|
| `auth = CRUDAuth(...)` singleton | `backend/src/infrastructure/auth/setup.py` |
| Dependencies | `backend/src/infrastructure/auth/dependencies.py` |
| OAuth configuration | `backend/src/infrastructure/auth/setup.py` |
| Login, logout and OAuth routes | `backend/src/infrastructure/auth/routes.py` |
| Refused-login and lockout hooks | `backend/src/infrastructure/auth/audit.py` |
| Session management routes | crudauth's `build_session_management_router`, mounted in `routes.py` |
| HTTP exceptions (fastcrud re-export) | `backend/src/infrastructure/http_exceptions.py` |
| Auth settings | `backend/src/infrastructure/config/settings.py` (`AuthSettings`) |

Session storage, CSRF, and lockout themselves live in the `crudauth` library, not the boilerplate.

---

[← Authentication Overview](index.md){ .md-button } [User Management →](user-management.md){ .md-button .md-button--primary }
