# Caching

The boilerplate ships a flexible caching system supporting **Redis or Memcached** server-side, plus configurable client-side cache headers. Same decorator and provider API regardless of the backend.

!!! tip "Building a full SaaS?"
    Caching is part of the free foundation. **[FastroAI](https://fastro.ai)** bundles it with Stripe payments, entitlements, transactional email, a frontend, and AI agents - all wired together and production-ready. [Ship your SaaS faster →](https://fastro.ai)

## Overview

Three layers, used together as needed:

- **`@cache` decorator** — Caches GET endpoints, automatically invalidates on any mutation (POST/PUT/PATCH/DELETE)
- **Provider API** — Direct cache operations (`get`, `set`, `delete`, etc.) for non-route code
- **Client-side cache headers** — `Cache-Control` headers added by middleware for browser caching

## Quick Example

```python
from typing import Annotated, Any
from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.cache import cache
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

The decorator caches the result for 600 seconds. PUT/PATCH/DELETE on the same `widget_id` invalidate the cache automatically. The first parameter must be `request: Request` — the decorator inspects the HTTP method.

## Architecture

```text
HTTP Request
    ↓
@cache decorator                  (decorator.py)
    ↓ (cache miss)
APIRouter handler
    ↓
service / FastCRUD                (your code)
    ↓
PostgreSQL
```

When the cache hits, the handler doesn't run at all — the cached value is returned directly. When it misses (or for mutations), the handler runs and the cache is updated or invalidated as configured.

## What's Included

| Component | Purpose | Location |
|-----------|---------|----------|
| `@cache` decorator | Endpoint-level caching with auto-invalidation | `infrastructure/cache/decorator.py` |
| Provider API | Direct cache ops (`get`, `set`, `delete`, …) | `infrastructure/cache/provider.py` |
| Redis backend | Pattern matching, persistence, rich types | `infrastructure/cache/backends/redis.py` |
| Memcached backend | Lightweight, key/value only | `infrastructure/cache/backends/memcached.py` |
| `ClientCacheMiddleware` | Adds `Cache-Control` headers | `infrastructure/middleware.py` |

## Configuration

```env
CACHE_ENABLED=true
CACHE_BACKEND=redis           # or "memcached"
DEFAULT_CACHE_EXPIRATION=3600

# Redis backend
CACHE_REDIS_HOST=redis        # use "localhost" without Docker
CACHE_REDIS_PORT=6379
CACHE_REDIS_DB=0
CACHE_REDIS_PASSWORD=
CACHE_REDIS_POOL_SIZE=10

# Memcached backend (only when CACHE_BACKEND=memcached)
CACHE_MEMCACHED_HOST=localhost
CACHE_MEMCACHED_PORT=11211
CACHE_MEMCACHED_POOL_SIZE=10

# Client-side cache headers
CLIENT_CACHE_ENABLED=true
CLIENT_CACHE_MAX_AGE=60        # seconds
```

When `CACHE_ENABLED=false`, the decorator becomes a no-op — useful in tests.

See [Environment Variables](../configuration/environment-variables.md#cache) for the full reference.

## Picking a Backend

Both backends work with the decorator and provider. They have different strengths:

| Feature | Redis | Memcached |
|---------|-------|-----------|
| Pattern-based deletion (`delete_pattern`) | Yes | No (raises `PatternMatchingNotSupportedError`) |
| Optional persistence (AOF / RDB) | Yes | No |
| Rich data structures (lists, sets, hashes) | Yes | Key/value only |
| Memory efficiency | Good | Excellent |

**Pick Redis** if you need pattern-based invalidation (`pattern_to_invalidate_extra` on the decorator, or `delete_pattern` directly), persistence across restarts, or you're already running Redis for sessions / rate limits / Taskiq.

**Pick Memcached** if you have an existing Memcached deployment or you specifically want simpler key/value semantics.

The boilerplate's defaults run Redis everywhere because it doubles as the session and rate-limit backend.

## Graceful Degradation

If the cache backend becomes unavailable, the decorator catches the error and falls through to the underlying handler. Your endpoints still work, just slower. This fail-open behavior is intentional — cached data is reproducible from the database, so cache failures shouldn't take the API down.

## Sub-pages

1. **[Redis Cache](redis-cache.md)** — Decorator usage, provider API, invalidation patterns
2. **[Client Cache](client-cache.md)** — `Cache-Control` headers and the client-cache middleware
3. **[Cache Strategies](cache-strategies.md)** — Patterns for cache key naming, related-key invalidation, and cache-aside flows

## Key Files

| Component | Location |
|-----------|----------|
| Decorator | `backend/src/infrastructure/cache/decorator.py` |
| Provider API | `backend/src/infrastructure/cache/provider.py` |
| Backends | `backend/src/infrastructure/cache/backends/` |
| Settings | `backend/src/infrastructure/config/settings.py` (`CacheSettings`) |
| Client-cache middleware | `backend/src/infrastructure/middleware.py` |

## Next Steps

Start with [Redis Cache](redis-cache.md) for the decorator and provider patterns, then look at [Cache Strategies](cache-strategies.md) for invalidation tactics.
