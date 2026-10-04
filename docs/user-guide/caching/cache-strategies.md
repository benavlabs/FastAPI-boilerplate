# Cache Strategies

Caching is easy to add and easy to get wrong. This page collects the practical patterns the boilerplate supports — how to name keys, when to invalidate, how to layer TTLs against write patterns, and how to warm the cache without bolting on a separate scheduler.

All examples use the boilerplate's real APIs: the [`@cache` decorator](redis-cache.md) for endpoint-level caching, and the provider exports (`get`, `set`, `delete`, `delete_pattern`, `exists`, `clear`) from `src.infrastructure.cache` for everything else.

## Picking a Key Naming Scheme

The decorator generates keys as `{formatted_key_prefix}:{resource_id}`. Your job is to pick a `key_prefix` (and any `{kwarg}` placeholders) that:

1. **Doesn't collide** with unrelated caches
2. **Matches your invalidation surface** — if you'll wipe by user, include the user identifier
3. **Reads cleanly** in `redis-cli KEYS '*'` while debugging

Patterns the codebase encourages:

```python
# Simple resource by id
@cache(key_prefix="widget", resource_id_name="widget_id")
# → widget:42

# Per-user list, paginated
@cache(key_prefix="user_{user_id}_widgets:page_{page}:size_{items_per_page}",
       resource_id_name="user_id")
# → user_5_widgets:page_1:size_10:5

# String IDs (usernames, slugs, hashed query strings)
@cache(key_prefix="user", resource_id_name="username", resource_id_type=str)
# → user:johndoe

# Time-windowed analytics — bake the window into the prefix
@cache(key_prefix="analytics_{user_id}_30d", resource_id_name="report_id")
# → analytics_5_30d:summary
```

**Avoid** prefixes that:

- Use raw resource IDs as the prefix (`{post_id}_comments`) — collisions are silent
- Include unbounded user input directly (`search:{raw_query}`) — hash long/free-text inputs first
- Mix unrelated resources at the same level (`data:42`) — debug nightmare

## Invalidation Strategies

There are essentially three invalidation strategies you'll combine:

### 1. TTL Only ("eventually correct")

Just expire the cache; never invalidate explicitly.

```python
@cache(key_prefix="popular_widgets", expiration=300)  # 5 minutes
async def get_popular(request: Request, ...):
    ...
```

**When to use:** read-only or near-read-only data where 1–5 minutes of staleness is acceptable. Reference data (countries, tier definitions), aggregates (top-N lists), expensive computations whose inputs change rarely.

**Don't use for:** anything a user just edited and expects to see immediately.

### 2. Write-Through Invalidation ("strict consistency")

Mutations on the same `(key_prefix, resource_id_name)` automatically delete the matching key. Add `to_invalidate_extra` for related caches:

```python
@router.patch("/{widget_id}")
@cache(
    key_prefix="widget",
    resource_id_name="widget_id",
    to_invalidate_extra={
        "user_widgets": "owner_id",      # invalidate the owner's list
        "widget_count": "global",        # invalidate the global counter
    },
)
async def update_widget(
    request: Request,
    widget_id: int,
    owner_id: int,
    ...,
) -> dict[str, Any]:
    return await widget_service.update(widget_id, values, db)
```

The decorator deletes the keys **after** the handler returns successfully — failed mutations don't touch the cache.

**When to use:** mutations to a resource that's directly cached, plus a small fixed set of related caches (this user's list, the global count, etc).

**Don't use for:** broad invalidations across many user-scoped lists — that's pattern-based territory.

### 3. Pattern-Based Invalidation ("blast radius")

For wipes that touch many keys at once (paginated lists, search caches), use pattern matching:

```python
@router.delete("/{widget_id}")
@cache(
    key_prefix="widget",
    resource_id_name="widget_id",
    pattern_to_invalidate_extra=[
        "user_{owner_id}_widgets:*",     # all paginated lists for this user
        "widget_search:*",                # all search-result caches
    ],
)
async def delete_widget(request: Request, widget_id: int, owner_id: int, ...) -> None:
    await widget_service.delete(widget_id, db)
```

!!! warning "Memcached doesn't support patterns"
    `pattern_to_invalidate_extra` raises `PatternMatchingNotSupportedError` when `CACHE_BACKEND=memcached`. The non-pattern delete still happens. Use Redis if you need pattern-based invalidation.

**When to use:** paginated or filtered lists where you don't know how many keys exist, search-result caches, anything where the prefix is a stable namespace.

**Don't use for:** narrow invalidations — you're scanning Redis on every mutation, which is much more expensive than a single `DEL`.

## Combining the Three

Real services usually mix all three:

```python
@router.put("/{widget_id}")
@cache(
    key_prefix="widget",
    resource_id_name="widget_id",
    expiration=900,                                       # TTL fallback (15 min)
    to_invalidate_extra={                                 # narrow related-key wipes
        "widget_count": "global",
    },
    pattern_to_invalidate_extra=[                         # broad list wipes
        "user_{owner_id}_widgets:*",
        "widget_search:*",
    ],
)
async def update_widget(request: Request, widget_id: int, owner_id: int, ...) -> dict[str, Any]:
    return await widget_service.update(widget_id, values, db)
```

The TTL is your safety net — even if you forget an invalidation, the cache self-heals within 15 minutes.

## Cache Aside (Service-Layer Caching)

The decorator covers route-level caching. For caching inside services or background tasks, use the provider API directly:

```python
from src.infrastructure.cache.provider import get, set, delete

KEY_TTL = 1800  # 30 minutes


async def get_user_score(user_id: int, db: AsyncSession) -> int:
    cache_key = f"user_score:{user_id}"

    # Try the cache first
    cached = await get(key=cache_key)
    if cached is not None:
        return int(cached)

    # Miss — compute and store
    score = await _compute_user_score(user_id, db)
    await set(key=cache_key, value=score, expiration=KEY_TTL)
    return score


async def invalidate_user_score(user_id: int) -> None:
    await delete(key=f"user_score:{user_id}")
```

Conventions:

- **Always use the same key format** in both the read and the invalidate path — copy/paste mistakes here are the most common cause of "cache won't update"
- **Compute first, write second.** Never `set` a value before you've successfully computed it; you'd cache an error.
- **Use the same TTL across reads and refreshes** so behavior is predictable.

## Cache Stampede Mitigation

When a hot cache key expires, every concurrent request can hit the database before any of them writes the new value back — a stampede. Mitigations the boilerplate's stack supports:

### Slightly Randomized TTLs

Pick TTLs in a range, not a single value, so a thousand keys created at the same time don't expire in lockstep:

```python
import random

ttl = 1800 + random.randint(-60, 60)  # 30 min ± 1 min
await set(key=cache_key, value=payload, expiration=ttl)
```

This is enough for most workloads.

### Refresh Ahead of Expiration

Inside the service, decide based on a "soft" TTL whether to recompute opportunistically:

```python
SOFT_TTL = 1500  # 25 min — recompute eagerly past this
HARD_TTL = 1800  # 30 min — fail-open beyond this

async def get_payload(user_id: int) -> dict:
    cache_key = f"user_payload:{user_id}"
    payload = await get(key=cache_key)

    if payload is not None and payload.get("computed_at", 0) > time.time() - SOFT_TTL:
        return payload  # fresh enough

    fresh = await _compute(user_id)
    fresh["computed_at"] = time.time()
    await set(key=cache_key, value=fresh, expiration=HARD_TTL)
    return fresh
```

Past the soft TTL, the next request triggers a recompute even though the cache is still warm — the next concurrent request still gets the fresh value. This is enough to prevent stampedes for moderately hot keys.

For genuinely hot keys (top trending list with 10k req/s), reach for a distributed lock (`SET key value NX EX 30`) inside the recompute path. The boilerplate doesn't ship one, but Redis primitives are sufficient.

## Cache Warming

Cache warming proactively populates the cache so the first user request after a deploy isn't a cold miss. Two reasonable places to do it in the boilerplate:

### At Application Startup (in the lifespan)

The boilerplate's `lifespan_factory` (in `infrastructure/app_factory.py`) is where the cache is initialized. Warming sits naturally just after that point — but only for genuinely **small** datasets (reference tables, tier definitions, top-N aggregates). Don't pull a million rows into Redis on every boot.

The pattern, in your own `interfaces/main.py` setup:

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI

from src.infrastructure.app_factory import lifespan_factory
from src.infrastructure.cache.provider import set
from src.infrastructure.config.settings import get_settings
from src.wiring.app import LIFECYCLES


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    # Run the boilerplate's default lifespan first
    base_lifespan = lifespan_factory(settings, lifecycles=LIFECYCLES)
    async with base_lifespan(app):
        await _warm_reference_data()
        yield


async def _warm_reference_data():
    # Small, slow-changing data — safe to warm at boot.
    tiers = await _load_all_tiers()
    for tier in tiers:
        await set(key=f"tier:{tier['id']}", value=tier, expiration=86400)
```

Wire it by passing `lifespan=lifespan` to `create_application()`.

### As a Taskiq Task

For larger or periodic warming, use a Taskiq task on a schedule. See [Background Tasks](../background-tasks/index.md) for the worker setup; the warming logic is the same — fetch data, call `set()`.

```python
# backend/src/modules/cache/tasks.py
from ...infrastructure.cache.provider import set
from ...infrastructure.taskiq.brokers import default_broker


@default_broker.task(task_name="warm_top_widgets")
async def warm_top_widgets() -> None:
    top = await _query_top_widgets(limit=100)
    await set(key="top_widgets", value=top, expiration=600)
```

Schedule it to run every 5 minutes (or whatever's shorter than the TTL) and the cache is always warm.

## Negative Caching

When a lookup misses the database too, cache the miss for a short window so subsequent requests don't re-hit the database:

```python
from src.infrastructure.cache.provider import get, set

NEGATIVE_TTL = 60  # 1 minute — keep negative caches very short
SENTINEL = "__NOT_FOUND__"


async def get_widget(widget_id: int, db: AsyncSession) -> dict | None:
    cache_key = f"widget:{widget_id}"
    cached = await get(key=cache_key)

    if cached == SENTINEL:
        return None
    if cached is not None:
        return cached

    result = await widget_service.get_by_id(widget_id, db)
    if result is None:
        await set(key=cache_key, value=SENTINEL, expiration=NEGATIVE_TTL)
        return None

    await set(key=cache_key, value=result, expiration=600)
    return result
```

Keep negative TTLs **much shorter** than positive ones — the row will appear eventually and you don't want users to keep getting 404s for a minute after creation.

## Per-User vs Global Caches

The single biggest mistake when adding `@cache` to an endpoint that returns user-specific data is keying only by resource ID. Two concrete problems:

```python
# WRONG — every user gets user 1's data
@router.get("/me/dashboard")
@cache(key_prefix="dashboard", resource_id_name="user_id")
async def my_dashboard(request: Request, user_id: int, ...):
    ...
```

Multiple users hit `dashboard:1` (the user_id of the first cached request) and see each other's data. Two fixes:

```python
# Include user in the prefix
@cache(key_prefix="dashboard_for_user_{user_id}", resource_id_name="user_id")
# → dashboard_for_user_5:5  ← key includes user

# Or just don't cache personalized responses
# (often the right call — Redis hits add latency for hot per-user data anyway)
```

## Picking TTLs

Default is one hour (`3600`). Override per route based on staleness tolerance:

| Data shape                                    | Suggested TTL              |
|-----------------------------------------------|----------------------------|
| Static reference data (tier list, countries)  | 24 hours (`86400`)         |
| User profile / public objects                 | 5–30 minutes (`300`–`1800`)|
| Paginated list endpoints                      | 1–5 minutes (`60`–`300`)   |
| Search results                                | 5–15 minutes (`300`–`900`) |
| Frequently changing dashboards                | 30–60 seconds              |
| Negative caches (404 lookups)                 | 30–120 seconds             |

When in doubt, start short. It's cheap to raise a TTL once you trust the invalidation paths — much harder to debug stale-data complaints from a 24-hour cache.

## Operational Notes

### Read your keys in production

```bash
redis-cli -h $CACHE_REDIS_HOST KEYS 'widget:*'
redis-cli -h $CACHE_REDIS_HOST TTL widget:42
redis-cli -h $CACHE_REDIS_HOST GET widget:42
```

If you can't tell from the key alone what's cached and how it's invalidated, your prefix is too short.

### Watch for fail-open behavior

The decorator catches Redis errors and falls through to the handler. That's good for availability but means you can have a "cache is down" outage that looks like a "DB is slow" outage on dashboards. Watch the logs for:

```
Cache backend not available: <error>
```

Alert on the rate of those, not just on Redis being unreachable.

### Don't cache personal data without thinking

If your handler returns different bodies depending on auth state, headers, or query params, those have to be in the key. The decorator only sees what you pass in `key_prefix` placeholders and `resource_id_name`.

## Anti-Patterns to Avoid

- **Caching mutation responses.** The decorator only caches GETs; if you find yourself wanting to cache a POST/PATCH response, you probably want to cache the underlying GET that's about to refresh anyway.
- **Reaching into the cache for state that's not derived from the database.** Cached state must be reconstructable. If losing the cache loses real data, you needed a DB row, not a cache key.
- **Mixing TTLs across paginated pages.** `widgets:page_1` expiring an hour before `widgets:page_2` produces inconsistent pagination. Use the same TTL across the entire prefix family.
- **Pattern invalidation on every mutation.** Pattern scans get expensive at scale. Reach for them only when you genuinely need to wipe many keys at once.

## Key Files

| Component             | Location                                              |
|-----------------------|-------------------------------------------------------|
| Decorator             | `backend/src/infrastructure/cache/decorator.py`       |
| Provider API          | `backend/src/infrastructure/cache/provider.py`        |
| Backends              | `backend/src/infrastructure/cache/backends/`          |
| Lifespan integration  | `backend/src/infrastructure/app_factory.py`           |

## Next Steps

- **[Redis Cache](redis-cache.md)** — Decorator parameters and provider API reference
- **[Client Cache](client-cache.md)** — `Cache-Control` headers for browser caching
- **[Background Tasks](../background-tasks/index.md)** — Scheduling cache warming jobs with Taskiq
