# Server-Side Cache (Redis or Memcached)

Server-side caching stores responses keyed by request shape so subsequent identical requests skip the database. This page covers the `@cache` decorator and the provider API.

The same code works against Redis or Memcached — pick via `CACHE_BACKEND`. The "Redis" label on this page is historical; everything below works for both backends unless explicitly called out.

## The `@cache` Decorator

The decorator handles caching for GET endpoints and invalidation for mutations.

### Basic Usage

```python
from typing import Annotated, Any
from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.cache.decorator import cache
from ...infrastructure.database.session import async_session
from .schemas import WidgetRead
from .service import WidgetService

router = APIRouter()


@router.get("/{widget_id}", response_model=WidgetRead)
@cache(key_prefix="widget", resource_id_name="widget_id", expiration=600)
async def get_widget(
    request: Request,
    widget_id: int,
    db: Annotated[AsyncSession, Depends(async_session)],
    widget_service: Annotated[WidgetService, Depends(get_widget_service)],
) -> dict[str, Any]:
    return await widget_service.get_by_id(widget_id, db)
```

The decorator builds the cache key as `widget:{widget_id}`. On cache hits, the handler doesn't run — the cached value is returned directly.

!!! warning "`request: Request` is required"
    The decorator inspects `request.method` to decide whether to read or invalidate. The first parameter of every decorated route must be `request: Request`. Without it the decorator raises an error.

### How It Works

1. **GET requests**: check the cache → return on hit, run the handler + cache the response on miss.
   An empty answer (`[]`, `{}`, `""`) is cached and served like any other, so a page with nothing on
   it isn't re-read on every request
2. **PUT/PATCH/POST/DELETE**: run the handler, then **delete** the cache key for the same
   `(key_prefix, resource_id)` — the write's own query string is not part of that key, so what it
   clears is the entry for the resource and not an entry nobody stored. A listing's pages each have
   their own key, so clearing all of them needs `pattern_to_invalidate_extra`
3. **Fail-open**: if the cache backend errors out, the decorator logs a warning and falls through to run the handler. Your endpoint stays available

### Decorator Parameters

```python
@cache(
    key_prefix: str,                                  # required — cache namespace
    resource_id_name: Any = None,                     # name of the parameter holding the resource ID
    expiration: int = 3600,                           # TTL in seconds (default: 1 hour)
    resource_id_type: type | tuple[type, ...] = int,  # expected type when auto-inferring
    to_invalidate_extra: dict[str, Any] | None = None,
    pattern_to_invalidate_extra: list[str] | None = None,
    backend_name: str | None = None,                  # if you've registered multiple backends
    per_caller: bool = True,                          # one entry per caller, unless the response is shared
)
```

The key is `prefix[:resource_id][:q=sorted query][:u=caller]`. Two pages of one listing, and two
callers of one route, never share an entry.

### `key_prefix` — Cache Namespace

The prefix can use `{kwarg_name}` placeholders to interpolate route parameters:

```python
@cache(key_prefix="widget", ...)
# → "widget:42"

@cache(key_prefix="user_{username}_widgets", ...)
# → "user_johndoe_widgets:42"

@cache(key_prefix="user_{user_id}_widgets:page_{page}:size_{items_per_page}", ...)
# → "user_5_widgets:page_1:size_10:42"
```

The `{...}` placeholders are interpolated from the route handler's keyword arguments (path/query parameters and dependencies).

### `resource_id_name` — Which Argument is the ID

The decorator appends `:{resource_id}` to the prefix. Resource ID resolution:

```python
# Explicit — recommended
@cache(key_prefix="widget", resource_id_name="widget_id", expiration=600)
async def get_widget(request: Request, widget_id: int, ...): ...

# Implicit — the decorator infers from the kwargs (looks for an int argument by default)
@cache(key_prefix="widget", expiration=600)
async def get_widget(request: Request, widget_id: int, ...): ...

# String IDs — set resource_id_type
@cache(key_prefix="user", resource_id_name="username", resource_id_type=str)
async def get_user(request: Request, username: str, ...): ...
```

If the decorator can't infer a resource ID, the key simply has no id part — which is what a
listing wants, since its query string already identifies the page.

### `per_caller` — Who the Entry Belongs To

By default each caller gets their own entry, keyed by the `user_id` of a `Principal` argument or the
`id` in a `current_user` mapping. A route whose response is identical for everyone passes
`per_caller=False` to share one entry; see
[Per-Caller vs Shared Caches](cache-strategies.md#per-caller-vs-shared-caches) for when that is
safe. A route that keeps the default but resolves no caller is **not cached at all**: the decorator
logs a warning and calls through, rather than hand one person's response to the next.

### What ships cached

`GET /api/v1/rate-limits/` is the one shipped route with the decorator on it: a superuser-only
listing of tier configuration, the same for every caller (`per_caller=False`), cached for
`RATE_LIMITS_CACHE_SECONDS`. Its `PATCH` and `DELETE` carry
`pattern_to_invalidate_extra=["rate_limits:*"]`, so a change clears every cached page. Pattern
invalidation needs a backend that supports it — Redis does; the memcached backend logs that it
cannot.

It reaches the decorator through `wiring/cache.py` rather than importing it:

```python
from ...wiring.cache import cached

@cached(key_prefix="rate_limits", per_caller=False)
```

The cache is a feature a project can remove, so the wiring hands a route either the real decorator
or `infrastructure/uncached.py`, which returns the route unchanged. A route therefore asks for
caching without depending on whether this project kept the cache.

## Invalidation

### Automatic on Mutations

Any non-GET method on a route decorated with the same `(key_prefix, resource_id_name)` automatically invalidates that key:

```python
@router.patch("/{widget_id}")
@cache(key_prefix="widget", resource_id_name="widget_id")
async def update_widget(request: Request, widget_id: int, ...) -> dict[str, Any]:
    # PATCH automatically deletes "widget:{widget_id}" after the handler runs
    return await widget_service.update(widget_id, values, db)
```

The cache deletion happens **after** the handler returns successfully. If the handler raises, the cache isn't touched.

### Invalidating Related Keys (`to_invalidate_extra`)

When mutating a resource, you often need to invalidate other caches that reference it. Use `to_invalidate_extra` — a dict of `{prefix: id_kwarg}`:

```python
@router.post("/")
@cache(
    key_prefix="widget",
    resource_id_name="widget_id",
    to_invalidate_extra={
        "user_widgets": "owner_id",      # also invalidate "user_widgets:{owner_id}"
        "widget_count": "global",        # invalidate "widget_count:global"
    },
)
async def create_widget(
    request: Request,
    widget: WidgetCreate,
    owner_id: int,
    ...,
) -> dict[str, Any]:
    return await widget_service.create(widget, owner_id, db)
```

The `id_kwarg` value can be a literal (like `"global"`) or a placeholder reference (`"owner_id"` resolves from the route's kwargs).

!!! note "Only on mutations"
    `to_invalidate_extra` and `pattern_to_invalidate_extra` are not allowed on GET routes — the decorator raises `InvalidRequestError` if you try. Cache invalidation only happens on PUT/PATCH/POST/DELETE.

### Pattern-Based Invalidation (`pattern_to_invalidate_extra`)

For bulk wipes, use Redis pattern matching:

```python
@router.delete("/{widget_id}")
@cache(
    key_prefix="widget",
    resource_id_name="widget_id",
    pattern_to_invalidate_extra=[
        "user_{owner_id}_widgets:*",       # all paginated lists for this user
        "widget_search:*",                  # all search result caches
    ],
)
async def delete_widget(
    request: Request,
    widget_id: int,
    owner_id: int,
    ...,
) -> None:
    await widget_service.delete(widget_id, db)
```

**Memcached doesn't support patterns.** When `CACHE_BACKEND=memcached`, `pattern_to_invalidate_extra` raises `PatternMatchingNotSupportedError` (logged at error level). The non-pattern delete still happens.

## The Provider API

For cache operations outside of routes (background jobs, services, scripts), use the provider API directly:

```python
from src.infrastructure.cache.provider import (
    cache_provider,
    clear,
    delete,
    delete_pattern,
    exists,
    get,
    set,
)


# Store a value (any JSON-serializable type)
await set(key="config:site_name", value="My App", expiration=3600)

# Retrieve it
value = await get(key="config:site_name")

# Existence check
if await exists(key="config:site_name"):
    ...

# Delete a key
await delete(key="config:site_name")

# Delete by pattern (Redis only)
await delete_pattern(pattern="user:42:*")

# Clear everything
await clear()
```

Values are serialized via `fastapi.encoders.jsonable_encoder` automatically — you can store dicts, lists, and any JSON-compatible structure.

## Cache Key Conventions

The decorator generates keys as:

```
{formatted_key_prefix}:{resource_id}
```

A few patterns the codebase uses:

| Pattern | Use case |
|---------|----------|
| `widget:42` | Single resource by id |
| `user_widgets:5` | List of a user's widgets |
| `user_{username}_widgets:page_{page}` | Paginated list scoped to a user |
| `search:{query_hash}` | Hashed search query |
| `analytics_{user_id}_30d:report` | Time-windowed analytics |

Pick prefixes that:

1. **Are unique** — never let two unrelated caches collide on the same key
2. **Match how you'll invalidate** — if you'll wipe by user, include the user identifier
3. **Are predictable** — anyone debugging should be able to read the key and know what's in it

## Configuration

```env
CACHE_ENABLED=true
CACHE_BACKEND=redis              # or "memcached"

# Redis backend
CACHE_REDIS_HOST=redis           # use "localhost" without Docker
CACHE_REDIS_PORT=6379
CACHE_REDIS_DB=0
CACHE_REDIS_PASSWORD=
CACHE_REDIS_CONNECT_TIMEOUT=5
CACHE_REDIS_POOL_SIZE=10
```

When `CACHE_ENABLED=false`, the decorator becomes a no-op (the handler runs every time). Use this in tests or when isolating performance issues.

## Picking Expiration Times

| Data shape | Suggested TTL |
|------------|---------------|
| Static reference data (e.g. country list, tier list) | 24 hours (`86400`) |
| User profile / public objects | 5–30 minutes (`300`–`1800`) |
| Paginated list endpoints | 1–5 minutes (`60`–`300`) |
| Search results | 5–15 minutes (`300`–`900`) |
| Frequently changing dashboards | 30–60 seconds |

Default is 1 hour (`3600`). Override per route based on staleness tolerance.

## Real Examples

The boilerplate doesn't currently use `@cache` on its built-in routes (the existing endpoints are admin/list operations where the data churns enough that caching isn't a clear win). Add `@cache` to your own modules where it pays off — typically: read-heavy GETs on rarely-changing data.

## Performance Tips

### Use `schema_to_select` Together with Caching

When the underlying CRUD call uses `schema_to_select=WidgetRead`, the cached payload is the trimmed dict — smaller cache values, faster serialization on hit.

### Don't Cache Personalized Responses Globally

If your handler returns different data per user but the cache key only includes the resource ID, **users see each other's data**. Either:

- Include `user_id` in the prefix: `key_prefix="widget_for_user_{user_id}"`
- Don't cache it

### Cache the Response, Not the Computation

The decorator caches the route handler's return value. If you need to cache an expensive sub-computation but not the whole response, use the provider API directly inside your service.

### Watch Pool Saturation

Default `CACHE_REDIS_POOL_SIZE=10` is enough for typical workloads. If you have very high concurrency on cached endpoints, raise it. Watch the application logs for `redis.exceptions.ConnectionError` — that often means pool exhaustion.

## Graceful Degradation

If the cache backend is unreachable, the decorator catches the error and falls through to run the handler. Your endpoint keeps working at non-cached speed. This fail-open behavior is intentional — cached data is reproducible from the database, so cache outages shouldn't take the API down.

You'll see a warning in the logs:

```
Cache backend not available: <error>
```

That's your signal to investigate the cache infrastructure.

## Troubleshooting

### Decorator never reads from cache

Check that `request: Request` is the first parameter of the decorated function. Without it, the decorator can't determine the HTTP method and can't decide whether to cache or invalidate.

### Pattern invalidation fails on Memcached

`PatternMatchingNotSupportedError` is expected — Memcached doesn't support pattern operations. Either switch to Redis or invalidate keys explicitly via `to_invalidate_extra`.

### Cached data is stale after a mutation

The mutation route needs the **same `(key_prefix, resource_id_name)`** as the GET route. If your `PATCH /widgets/{widget_id}` uses `key_prefix="widget"` and your `GET /widgets/{widget_id}` uses `key_prefix="widget_cache"`, they won't talk to each other.

### Cache returns the wrong user's data

You're keying by resource ID without including the user. See "Don't Cache Personalized Responses Globally" above.

## Key Files

| Component | Location |
|-----------|----------|
| Decorator | `backend/src/infrastructure/cache/decorator.py` |
| Provider API | `backend/src/infrastructure/cache/provider.py` |
| Redis backend | `backend/src/infrastructure/cache/backends/redis.py` |
| Memcached backend | `backend/src/infrastructure/cache/backends/memcached.py` |
| Settings | `backend/src/infrastructure/config/settings.py` (`CacheSettings`) |

## Next Steps

- **[Client Cache](client-cache.md)** — `Cache-Control` headers for browser caching
- **[Cache Strategies](cache-strategies.md)** — Patterns for keys, related-key invalidation, cache-aside flows
- **[Environment Variables](../configuration/environment-variables.md#cache)** — Full settings reference
