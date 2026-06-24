# Rate Limiting

The boilerplate ships a flexible rate limiter that supports per-tier, per-path limits with Redis or Memcached backends. This page covers how the pieces fit together, how to enable enforcement on your routes, and the gotchas to know upfront.

!!! tip "Building a full SaaS?"
    Rate limiting is part of the free foundation. **[FastroAI](https://fastro.ai)** bundles it with Stripe payments, entitlements, transactional email, a frontend, and AI agents - all wired together and production-ready. [Ship your SaaS faster →](https://fastro.ai)

## What's Built In

```text
backend/src/infrastructure/rate_limit/
├── base.py            RateLimiterBackend abstract base
├── backends/          Redis and Memcached implementations
├── exceptions.py      RateLimitException, RateLimiterBackendException
├── initialize.py      initialize_rate_limiter() / close_rate_limiter()
├── middleware.py      RateLimiterMiddleware + check_rate_limit dependency
├── provider.py        increment_and_check, get_count, reset
└── utils.py           sanitize_path

backend/src/modules/rate_limit/
├── models.py          RateLimit (tier_id, path, limit, period)
├── routes.py          GET / GET-by-name / PATCH / DELETE on /api/v1/rate-limits/
├── crud.py / service.py
└── schemas.py
```

The middleware and provider are wired up; the backend is initialized in the app's lifespan. **Enforcement is opt-in per route** — see below.

## How a Request Flows Through It

1. **Request arrives**, `RateLimiterMiddleware` is on the stack but **does not enforce limits** — it only attaches `X-RateLimit-*` headers to the response after the handler runs.
2. **The route's `Depends(check_rate_limit)` runs.** This is the actual enforcement point. Without this dependency on a route, no limit is checked.
3. **`check_rate_limit` extracts the user** from `request.state.user` (or falls back to client IP for anonymous requests), looks up the user's tier and the matching rate-limit row from the database, and computes `(limit, period)`.
4. **`increment_and_check`** atomically increments the counter at `ratelimit:{user_or_ip}:{sanitized_path}` and returns `(count, is_limited)`. The TTL on the key is set on first increment to `period` seconds.
5. **If `is_limited`**, raises `RateLimitException` (HTTP 429). Otherwise, sets `request.state.rate_limit_headers` so the middleware can attach them to the response.

The key shape (no window suffix — the TTL handles the window):

```text
ratelimit:{user_id_or_ip}:{sanitized_path}
```

## Enabling Enforcement on a Route

Add the dependency:

```python
from fastapi import APIRouter, Depends
from src.infrastructure.rate_limit import check_rate_limit

router = APIRouter()


@router.post("/widgets", dependencies=[Depends(check_rate_limit)])
async def create_widget(...): ...
```

Or apply it to every route in a router:

```python
router = APIRouter(dependencies=[Depends(check_rate_limit)])
```

That's all that's required — provided the rate limiter is enabled (`RATE_LIMITER_ENABLED=true`), every request to that route is checked.

!!! warning "Currently no built-in route uses `check_rate_limit`"
    The boilerplate's shipped routes (`/api/v1/users`, `/api/v1/auth`, `/api/v1/tiers`, `/api/v1/rate-limits`, `/api/v1/api-keys`) do **not** apply `check_rate_limit` by default. You add the dependency where you want enforcement. The middleware will still attach `X-RateLimit-*` headers, but only when something has populated `request.state.rate_limit_headers` — which only happens after `check_rate_limit` has run.

## Configuration

```env
# Master toggle
RATE_LIMITER_ENABLED=true

# Backend selection (mirrors the cache backend selector)
RATE_LIMITER_BACKEND=redis            # or "memcached"

# Behavior on backend errors:
#   true  → log and let the request through (recommended)
#   false → raise RateLimitException ("Access denied as a precaution")
RATE_LIMITER_FAIL_OPEN=true

# Defaults applied when the user has no tier or no matching rate-limit row
DEFAULT_RATE_LIMIT_LIMIT=100
DEFAULT_RATE_LIMIT_PERIOD=60          # seconds — 100/60s by default

# Redis backend (when RATE_LIMITER_BACKEND=redis)
RATE_LIMITER_REDIS_HOST=redis         # use "localhost" without Docker
RATE_LIMITER_REDIS_PORT=6379
RATE_LIMITER_REDIS_DB=1               # rate-limiter DB (cache + session share DB 0, taskiq DB 3)
RATE_LIMITER_REDIS_PASSWORD=
RATE_LIMITER_REDIS_CONNECT_TIMEOUT=5
RATE_LIMITER_REDIS_POOL_SIZE=10

# Memcached backend (when RATE_LIMITER_BACKEND=memcached)
RATE_LIMITER_MEMCACHED_HOST=localhost
RATE_LIMITER_MEMCACHED_PORT=11211
RATE_LIMITER_MEMCACHED_POOL_SIZE=10
```

When `RATE_LIMITER_ENABLED=false`, `check_rate_limit` returns immediately — the dependency is a no-op. Useful in tests and for isolating performance issues.

## User-Tier vs IP-Based Limits

The rate limiter has two paths depending on whether `request.state.user` is set:

```python
# Inside _check_rate_limit
if user:
    user_id = user["id"]
    tier = await crud_tiers.get(db=db, id=user["tier_id"], ...)
    if tier:
        rate_limit = await crud_rate_limits.get(db=db, tier_id=tier["id"], path=sanitized_path, ...)
        if rate_limit:
            limit, period = rate_limit["limit"], rate_limit["period"]
        else:
            limit, period = DEFAULT_LIMIT, DEFAULT_PERIOD
    else:
        limit, period = DEFAULT_LIMIT, DEFAULT_PERIOD
else:
    # Anonymous — key by client IP
    user_id = request.client.host
    limit, period = DEFAULT_LIMIT, DEFAULT_PERIOD
```

!!! warning "`request.state.user` is not populated automatically"
    The default session auth dependency (`get_current_user`) does not write the user back to `request.state.user`. Until you add a small helper that does, **every request looks anonymous to the rate limiter**, and tier-specific limits won't apply.

A minimal middleware to bridge the two:

Session validation now lives in the `crudauth` library — the `auth` singleton in `infrastructure/auth/setup.py` resolves the cookie (and enforces CSRF/lockout) and yields a `Principal`. The simplest way to bring the user into the rate limiter is at the route layer: depend on `get_optional_user` (from `infrastructure/auth/dependencies.py`) and stash the result on `request.state.user` before the limiter reads it.

```python
# a router-level dependency you can attach where tier limits matter
from typing import Annotated, Any

from fastapi import Depends, Request

from src.infrastructure.auth.dependencies import get_optional_user


async def attach_user_to_request(
    request: Request,
    user: Annotated[dict[str, Any] | None, Depends(get_optional_user)],
) -> None:
    if user is not None:
        request.state.user = user
```

crudauth owns the cookie/CSRF/lockout validation, so you never re-implement session lookup — you only reuse the resolved user. (A pure-Starlette middleware can't run FastAPI dependencies, which is why this is wired as a dependency rather than as middleware.)

For most teams, IP-based default limits (`100 req/60s`) are enough until you have an actual product reason to bring tiers into the rate-limit story.

## Path Sanitization

Paths are normalized for consistent keys:

```python
def sanitize_path(path: str) -> str:
    return path.strip("/").replace("/", "_")

# /api/v1/users         → "api_v1_users"
# /api/v1/users/42      → "api_v1_users_42"
# /api/v1/users/{id}    → "api_v1_users_{id}"
```

The middleware first looks up the `RateLimit` row by sanitized path. If nothing matches, it falls back to looking up the original path. **In practice you should store the sanitized form in the database** — that's what the lookup primarily uses, and it's what the cache key format mirrors.

Note: paths with path parameters (`/users/42`) sanitize to `api_v1_users_42`, which means **each individual resource ID gets its own counter**. That's almost always what you want (otherwise a single hot resource could rate-limit unrelated reads), but if you specifically want a single counter for a parameterized route, store the rule under the literal pattern `api_v1_users_{id}` and write a small middleware that matches the route against the path template before sanitizing.

## Managing Rate-Limit Rules

The `RateLimit` model:

```python
class RateLimit(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "rate_limits"

    id: int
    tier_id: int        # FK to tiers.id
    name: str           # unique — used as the URL path on /rate-limits/{name}
    path: str           # sanitized path the rule applies to
    limit: int          # max requests per period
    period: int         # seconds
```

### What the API exposes

| Method | Path                         | Auth        | Notes                                    |
|--------|------------------------------|-------------|------------------------------------------|
| GET    | `/api/v1/rate-limits/`       | Public      | Paginated list of all rate-limit rules   |
| GET    | `/api/v1/rate-limits/{name}` | Public      | Get a rule by name                       |
| PATCH  | `/api/v1/rate-limits/{name}` | Superuser   | Update an existing rule                  |
| DELETE | `/api/v1/rate-limits/{name}` | Superuser   | Delete a rule                            |

There's **no POST endpoint** for creating rate-limit rules. To seed initial rules, you have three options:

### Option 1: SQL / Migration

Add an Alembic migration that inserts the rows:

```python
# alembic/versions/xxxx_seed_rate_limits.py
def upgrade():
    op.execute("""
        INSERT INTO rate_limits (tier_id, name, path, "limit", period, created_at)
        VALUES
            (1, 'free_widgets_create', 'api_v1_widgets', 10, 60, NOW()),
            (2, 'pro_widgets_create',  'api_v1_widgets', 100, 60, NOW())
    """)
```

### Option 2: Custom Seed Script

Add a one-off in `backend/scripts/`:

```python
# backend/scripts/setup_rate_limits.py
import asyncio

from src.infrastructure.database.session import local_session
from src.modules.rate_limit.crud import crud_rate_limits


async def main():
    async with local_session() as db:
        await crud_rate_limits.create(db=db, object={
            "tier_id": 1, "name": "free_widgets_create",
            "path": "api_v1_widgets", "limit": 10, "period": 60,
        })
        await db.commit()


if __name__ == "__main__":
    asyncio.run(main())
```

Run with `uv run python -m scripts.setup_rate_limits` (from `backend/`).

### Option 3: Add a SQLAdmin View

Mirror `UserAdmin` and `TierAdmin` to add a `RateLimitAdmin` view — see [Admin Panel → Adding Models](../admin-panel/adding-models.md). This gives you a UI for creating, editing, and deleting rules.

## Response Headers

When `check_rate_limit` runs successfully, the middleware attaches:

| Header                | Meaning                                          |
|-----------------------|--------------------------------------------------|
| `X-RateLimit-Limit`   | The configured limit for this user × path        |
| `X-RateLimit-Remaining` | How many requests are left in the current window |
| `X-RateLimit-Reset`   | Period (seconds) for the window                  |

These are standard-ish (formatted like the GitHub / Stripe convention, not RFC 6585). Frontends can read them to surface graceful "you're approaching your limit" UI.

## Programmatic Cache-like Operations

The provider exposes the same primitives the middleware uses, in case you need to apply rate limits outside the HTTP request path (background jobs that throttle calls to a third party, for example):

```python
from src.infrastructure.rate_limit import increment_and_check, get_count, reset

count, is_limited = await increment_and_check(
    key="external_api_calls:user_42",
    limit=100,
    period=3600,
    fail_open=True,
)

current = await get_count("external_api_calls:user_42")
await reset("external_api_calls:user_42")
```

Use a key prefix that doesn't collide with the HTTP rate limiter's `ratelimit:` namespace.

## Backend Differences

| Feature                     | Redis | Memcached |
|-----------------------------|-------|-----------|
| Atomic increment + TTL set  | Yes   | Yes       |
| `get_count` / `reset`       | Yes   | Yes       |
| Pattern-based reset         | Yes   | No        |
| Connection pooling          | Yes   | Yes       |

Both backends do everything the middleware needs. Pick Redis if you're already running it for cache or Taskiq.

## Production Considerations

### Pool sizing

`RATE_LIMITER_REDIS_POOL_SIZE=10` is enough for typical workloads. If you're seeing `redis.exceptions.ConnectionError` under load, it usually means pool exhaustion — raise the pool size or check upstream connection-leak issues first.

### Fail-open vs fail-closed

The default `RATE_LIMITER_FAIL_OPEN=true` means a Redis outage doesn't take your API down — requests pass through unrate-limited. This is the right call for most public APIs.

If you specifically need rate limits enforced even during cache outages (e.g. you're protecting an expensive AI inference endpoint that you don't want hammered), set `RATE_LIMITER_FAIL_OPEN=false`. Be aware: a flaky Redis connection now translates directly into 429s for users.

### Window behavior

The implementation uses a fixed-window counter (TTL on first increment). At the boundary between windows, a user can technically make `2 × limit` requests in a short span. For most use cases this is fine; if you need stricter sliding-window semantics, build that on top of the provider yourself.

### Anonymous-user limits

IP-based rate limits are easy to bypass with NAT / proxies / IPv6 rotation. They're a speed bump, not security. If you're trying to prevent abuse rather than control fair use, you need authentication, captchas, or upstream firewall rules — not just rate limits.

## Troubleshooting

### "I added `Depends(check_rate_limit)` but no headers appear"

- Confirm `RATE_LIMITER_ENABLED=true`
- Confirm the rate limiter initialized cleanly at startup (look for `Cache backend not available` or similar)
- Confirm the dependency runs **before** the response is built (it does, by virtue of being a dependency — but if you're seeing an empty body the route may have errored earlier)

### "All requests look anonymous even though users are logged in"

`request.state.user` isn't being populated. Either implement the bridge middleware shown above, or accept that the rate limiter operates on IP only.

### "Path lookups never find the rate-limit row"

Verify the `path` column in `rate_limits` matches the **sanitized** form (slashes replaced with underscores). The lookup tries sanitized first, then falls back to the original path — but keys in Redis always use the sanitized version, so configs should match.

### "The rate-limiter dependency raises `RateLimiterBackendException`"

The Redis connection failed and `RATE_LIMITER_FAIL_OPEN=false`. Either fix Redis, switch to fail-open, or temporarily disable the limiter (`RATE_LIMITER_ENABLED=false`).

## Key Files

| Component             | Location                                                  |
|-----------------------|-----------------------------------------------------------|
| Middleware + dependency | `backend/src/infrastructure/rate_limit/middleware.py`   |
| Provider API          | `backend/src/infrastructure/rate_limit/provider.py`       |
| Backend implementations | `backend/src/infrastructure/rate_limit/backends/`       |
| Path sanitization     | `backend/src/infrastructure/rate_limit/utils.py`          |
| RateLimit model       | `backend/src/modules/rate_limit/models.py`                |
| Rate-limit routes     | `backend/src/modules/rate_limit/routes.py`                |
| Settings              | `backend/src/infrastructure/config/settings.py` (`RateLimiterSettings`) |

## Next Steps

- **[Tiers](../authentication/permissions.md#tier-based-authorization)** — Setting up user tiers
- **[Admin Panel → Adding Models](../admin-panel/adding-models.md)** — Adding a `RateLimitAdmin` view
- **[Caching → Cache Strategies](../caching/cache-strategies.md)** — Patterns that share the same Redis-as-state mindset
