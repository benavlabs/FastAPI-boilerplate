# Caching

The boilerplate includes a comprehensive caching system built on Redis that improves performance through server-side caching and client-side cache control. This section covers the complete caching implementation.

## Overview

The caching system provides multiple layers of optimization:

- **Server-Side Caching**: Redis-based caching with automatic invalidation
- **Client-Side Caching**: HTTP cache headers for browser optimization  
- **Cache Invalidation**: Smart invalidation strategies for data consistency

## Quick Example

```python
from app.core.utils.cache import cache

@router.get("/posts/{post_id}")
@cache(key_prefix="post_cache", expiration=3600)
async def get_post(request: Request, post_id: int):
    # Cached for 1 hour, automatic invalidation on updates
    return await crud_posts.get(db=db, id=post_id)
```

## Architecture

### Server-Side Caching
- **Redis Integration**: Connection pooling and async operations
- **Decorator-Based**: Simple `@cache` decorator for endpoints
- **Smart Invalidation**: Automatic cache clearing on data changes
- **Pattern Matching**: Bulk invalidation using Redis patterns

### Client-Side Caching  
- **HTTP Headers**: Cache-Control headers for browser caching
- **Middleware**: Automatic header injection
- **Configurable TTL**: Customizable cache duration

## Key Features

**Automatic Cache Management**
- Caches GET requests automatically
- Invalidates cache on PUT/POST/DELETE operations
- Supports complex invalidation patterns

**Flexible Configuration**
- Per-endpoint expiration times
- Custom cache key generation
- Environment-specific Redis settings

**Performance Optimization**
- Connection pooling for Redis
- Efficient key pattern matching
- Minimal overhead for cache operations

## Getting Started

1. **[Redis Cache](redis-cache.md)** - Server-side caching with Redis
2. **[Client Cache](client-cache.md)** - Browser caching with HTTP headers  
3. **[Cache Strategies](cache-strategies.md)** - Invalidation patterns and best practices

Each section provides detailed implementation examples and configuration options for building a robust caching layer.

## Configuration

Basic Redis configuration in your environment:

```bash
# Redis Cache Settings
REDIS_CACHE_HOST=localhost
REDIS_CACHE_PORT=6379
```

The caching system automatically handles connection pooling and provides efficient cache operations for your FastAPI endpoints.

## Next Steps

Start with **[Redis Cache](redis-cache.md)** to understand the core server-side caching implementation, then explore client-side caching and advanced invalidation strategies. 