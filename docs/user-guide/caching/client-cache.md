# Client Cache

Client-side caching uses HTTP `Cache-Control` headers to tell browsers (and intermediate CDNs / proxies) when they're allowed to reuse a response without coming back to the server. The boilerplate ships a small middleware that sets sensible defaults — an explicit "don't cache" for the API, and a configurable `max-age` for everything else.

## What's Built In

```text
infrastructure/middleware.py        ClientCacheMiddleware
infrastructure/app_factory.py       Wires it into the app at startup
infrastructure/config/settings.py   CLIENT_CACHE_ENABLED, CLIENT_CACHE_MAX_AGE
```

That's the entire surface area. There's no per-route configuration, no path table, no ETag handling out of the box. The middleware is intentionally tiny — anything more nuanced you handle in your route handlers.

## How It Works

```python
# infrastructure/middleware.py
class ClientCacheMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app: ASGIApp,
        max_age: int = 60,
        public_prefixes: tuple[str, ...] = PUBLIC_CACHE_PREFIXES,
        api_prefix: str = "/api",
    ) -> None:
        ...

    async def dispatch(self, request, call_next):
        response = await call_next(request)
        if "cache-control" in response.headers:
            return response

        path = request.url.path
        if path.startswith(f"{self.api_prefix}/"):
            response.headers["Cache-Control"] = "private, no-cache, no-store, must-revalidate"
        elif path.startswith(self.public_prefixes):
            response.headers["Cache-Control"] = f"public, max-age={self.max_age}"
        else:
            response.headers["Cache-Control"] = "private, no-store"
        return response
```

Four rules:

| Path                                       | `Cache-Control` value                          |
|--------------------------------------------|------------------------------------------------|
| The route set the header itself            | whatever the route set                         |
| Under `API_PREFIX` (`/api` by default)     | `private, no-cache, no-store, must-revalidate` |
| Under a public prefix (`/admin/statics/`)  | `public, max-age={CLIENT_CACHE_MAX_AGE}`       |
| Anything else                              | `private, no-store`                            |

The reasoning:

- **The API** is dynamic, often authenticated, and frequently personalized. Caching at the browser or CDN would leak data between users and serve stale state. Default is hard "don't cache." The prefix comes from `API_PREFIX`, so moving the API moves this rule with it.
- **Public prefixes** are the paths whose bytes are the same for every caller — by default where SQLAdmin serves its own CSS and JS. Pass your own `public_prefixes` to add an application's static mount.
- **Everything else** — the admin pages, the docs, the health endpoints — answers with per-caller data or state, so a shared cache must not keep it. A route that knows its response is cacheable sets the header itself and is left alone.

## Configuration

```env
# Enables the middleware. Set to false to skip the Cache-Control header entirely.
CLIENT_CACHE_ENABLED=true

# max-age (seconds) used for non-API paths.
CLIENT_CACHE_MAX_AGE=60
```

The middleware is added when `CLIENT_CACHE_ENABLED` is true (`infrastructure/app_factory.py`). It has nothing to do with `CACHE_ENABLED`, which governs the server-side cache: either can be on without the other.

When `CLIENT_CACHE_ENABLED=false`, no `Cache-Control` header is set by middleware — your routes (or your reverse proxy) are responsible for it.

## Overriding for a Specific Endpoint

If you want a particular API endpoint to opt **into** browser caching, set the header in the handler. Middleware runs after the handler, so a header set in the route is overwritten — meaning you have to either set it via `Response` directly (and let the middleware overwrite anyway) **or** use a small route-level middleware. The simplest reliable pattern is to disable the global middleware in tests/docs and set headers explicitly in your routes:

```python
from fastapi import APIRouter, Response

router = APIRouter()


@router.get("/manifest.json")
async def manifest(response: Response) -> dict[str, str]:
    response.headers["Cache-Control"] = "public, max-age=86400, immutable"
    return {"name": "My App", "version": "1.0.0"}
```

Heads up: because the global middleware overwrites `Cache-Control` for `/api/*` paths, the snippet above only takes effect on **non-API** routes. For API routes you actually want to cache, either:

1. Mount them outside `/api/` (rare), or
2. Disable `CLIENT_CACHE_ENABLED` and set headers on a per-route basis.

In practice, almost no endpoint in a typical app benefits from browser caching of an API response — keep API caching server-side via the [`@cache` decorator](redis-cache.md) and let the browser fetch fresh.

## A Quick Cache-Control Primer

The directives the middleware uses (and the ones you'll most often add manually):

| Directive               | Meaning                                                                         |
|-------------------------|---------------------------------------------------------------------------------|
| `public`                | Any cache (browser, CDN, proxy) may store the response                          |
| `private`               | Only the end-user's browser may store it. CDNs / shared proxies must not        |
| `no-cache`              | Caches may store, but must revalidate with the server before reuse              |
| `no-store`              | Don't store at all — not in the browser, not on disk, not in a CDN              |
| `must-revalidate`       | Once stale, the cache must check upstream before serving again                  |
| `max-age=<seconds>`     | Cache is fresh for this many seconds                                            |
| `s-maxage=<seconds>`    | Same as `max-age`, but applies only to shared caches (CDNs)                     |
| `immutable`             | The body will never change — clients can skip revalidation entirely             |
| `stale-while-revalidate=<s>` | After freshness expires, serve the stale copy for this long while updating |

The pre-API value (`private, no-cache, no-store, must-revalidate`) is paranoid on purpose: in combination, those directives forbid every form of caching the major browsers and CDNs implement. That's the right default for authenticated dynamic data.

## When to Reach for ETags

The middleware doesn't generate ETags or `Last-Modified` headers. If you want conditional requests (`304 Not Modified` on unchanged resources), you have to set those headers in the handler:

```python
import hashlib
from fastapi import APIRouter, Request, Response, status

router = APIRouter()


@router.get("/manifest.json")
async def manifest(request: Request, response: Response) -> dict[str, str] | Response:
    payload = {"name": "My App", "version": "1.0.0"}
    body = str(payload).encode()
    etag = f'"{hashlib.md5(body).hexdigest()}"'

    if request.headers.get("if-none-match") == etag:
        return Response(status_code=status.HTTP_304_NOT_MODIFIED)

    response.headers["ETag"] = etag
    response.headers["Cache-Control"] = "public, max-age=300"
    return payload
```

ETags are most useful for:

- Larger static-ish payloads (manifests, configs, generated PDFs)
- Public endpoints with high read volume but low write volume
- Anything where the body is computed but stable across many requests

For typical CRUD endpoints they're rarely worth the complexity — `@cache` server-side plus a short `max-age` for genuinely static assets covers most cases.

## Reverse Proxy / CDN Considerations

If you serve the app behind a reverse proxy or CDN (Nginx, Caddy, CloudFront, Cloudflare), the proxy will see and obey the middleware's `Cache-Control` headers:

- `/api/*` responses won't be cached at the edge — every request reaches the origin
- Non-API responses are eligible for shared caching for `CLIENT_CACHE_MAX_AGE` seconds

If you need different behavior at the edge (longer CDN TTL but short browser TTL, for example), set both `s-maxage` and `max-age` from your handlers, or strip the middleware's header at the proxy and replace it.

## Disabling the Middleware

```env
CLIENT_CACHE_ENABLED=false
```

After restart, no `Cache-Control` header is set by the boilerplate. Your routes and proxy take full control. This is the right move when:

- You have a reverse proxy / CDN already managing cache headers
- You're doing per-route caching strategies that would be undone by the middleware
- You're debugging a caching-related bug and want a clean baseline

## Troubleshooting

### "My API response is still being cached by the browser"

Confirm the response actually carries the no-cache header:

```bash
curl -I http://localhost:8000/api/v1/users/me \
    -H "Cookie: session_id=..."
# look for: Cache-Control: private, no-cache, no-store, must-revalidate
```

If the header is missing, check that `CLIENT_CACHE_ENABLED=true` — that setting alone decides whether the middleware is mounted.

### "I want to cache an API response but the middleware overrides it"

The middleware overwrites `Cache-Control` for any `/api/*` path. Options:

- Cache server-side with the [`@cache` decorator](redis-cache.md) — almost always what you actually want
- Set `CLIENT_CACHE_ENABLED=false` and manage `Cache-Control` per-route
- Route the endpoint outside `/api/*` if it really is a static asset

### "Static assets aren't being cached aggressively enough"

Raise `CLIENT_CACHE_MAX_AGE`, or set per-asset headers in the handler / proxy. Browsers will use whichever value the server returns most recently, so updating the env var and redeploying takes effect for new requests immediately.

## Key Files

| Component             | Location                                              |
|-----------------------|-------------------------------------------------------|
| Middleware            | `backend/src/infrastructure/middleware.py`            |
| Wiring                | `backend/src/infrastructure/app_factory.py`           |
| Settings              | `backend/src/infrastructure/config/settings.py` (`CacheSettings`) |

## Next Steps

- **[Redis Cache](redis-cache.md)** — Server-side caching with the `@cache` decorator
- **[Cache Strategies](cache-strategies.md)** — Patterns for keys, related-key invalidation, cache-aside flows
- **[Environment Variables](../configuration/environment-variables.md#cache)** — Full settings reference
