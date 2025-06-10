# Rate Limiting

The boilerplate includes a sophisticated rate limiting system built on Redis that protects your API from abuse while supporting user tiers with different access levels. This system provides flexible, scalable rate limiting for production applications.

## Overview

Rate limiting controls how many requests users can make within a specific time period. The boilerplate implements:

- **Redis-Based Storage**: Fast, distributed rate limiting using Redis
- **User Tier System**: Different limits for different user types  
- **Path-Specific Limits**: Granular control per API endpoint
- **Fallback Protection**: Default limits for unauthenticated users

## Quick Example

```python
from fastapi import Depends
from app.api.dependencies import rate_limiter_dependency

@router.post("/api/v1/posts", dependencies=[Depends(rate_limiter_dependency)])
async def create_post(post_data: PostCreate):
    # This endpoint is automatically rate limited based on:
    # - User's tier (basic, premium, enterprise)  
    # - Specific limits for the /posts endpoint
    # - Default limits for unauthenticated users
    return await crud_posts.create(db=db, object=post_data)
```

## Architecture

### Rate Limiting Components

**Rate Limiter Class**: Singleton Redis client for checking limits
**User Tiers**: Database-stored user subscription levels
**Rate Limit Rules**: Path-specific limits per tier
**Dependency Injection**: Automatic enforcement via FastAPI dependencies

### How It Works

1. **Request Arrives**: User makes API request to protected endpoint
2. **User Identification**: System identifies user and their tier
3. **Limit Lookup**: Finds applicable rate limit for user tier + endpoint
4. **Redis Check**: Increments counter in Redis sliding window
5. **Allow/Deny**: Request proceeds or returns 429 Too Many Requests

## User Tier System

### Default Tiers

The system supports flexible user tiers with different access levels:

```python
# Example tier configuration
tiers = {
    "free": {
        "requests_per_minute": 10,
        "requests_per_hour": 100,
        "special_endpoints": {
            "/api/v1/ai/generate": {"limit": 2, "period": 3600},  # 2 per hour
            "/api/v1/exports": {"limit": 1, "period": 86400},     # 1 per day
        }
    },
    "premium": {
        "requests_per_minute": 60,
        "requests_per_hour": 1000,
        "special_endpoints": {
            "/api/v1/ai/generate": {"limit": 50, "period": 3600},
            "/api/v1/exports": {"limit": 10, "period": 86400},
        }
    },
    "enterprise": {
        "requests_per_minute": 300,
        "requests_per_hour": 10000,
        "special_endpoints": {
            "/api/v1/ai/generate": {"limit": 500, "period": 3600},
            "/api/v1/exports": {"limit": 100, "period": 86400},
        }
    }
}
```

### Rate Limit Database Structure

```python
# Rate limits are stored per tier and path
class RateLimit:
    id: int
    tier_id: int           # Links to user tier
    name: str             # Descriptive name
    path: str             # API path (sanitized)
    limit: int            # Number of requests allowed
    period: int           # Time period in seconds
```

## Implementation Details

### Automatic Rate Limiting

The system automatically applies rate limiting through dependency injection:

```python
@router.post("/protected-endpoint", dependencies=[Depends(rate_limiter_dependency)])
async def protected_endpoint():
    """This endpoint is automatically rate limited."""
    pass

# The dependency:
# 1. Identifies the user and their tier
# 2. Looks up rate limits for this path
# 3. Checks Redis counter
# 4. Allows or blocks the request
```

### Redis-Based Counting

The rate limiter uses Redis for distributed, high-performance counting:

```python
# Sliding window implementation
async def is_rate_limited(self, user_id: int, path: str, limit: int, period: int) -> bool:
    current_timestamp = int(datetime.now(UTC).timestamp())
    window_start = current_timestamp - (current_timestamp % period)
    
    # Create unique key for this user/path/window
    key = f"ratelimit:{user_id}:{sanitized_path}:{window_start}"
    
    # Increment counter
    current_count = await redis_client.incr(key)
    
    # Set expiration on first increment
    if current_count == 1:
        await redis_client.expire(key, period)
    
    # Check if limit exceeded
    return current_count > limit
```

### Path Sanitization

API paths are sanitized for consistent Redis key generation:

```python
def sanitize_path(path: str) -> str:
    return path.strip("/").replace("/", "_")

# Examples:
# "/api/v1/users" → "api_v1_users"
# "/posts/{id}" → "posts_{id}"
```

## Configuration

### Environment Variables

```bash
# Rate Limiting Settings
DEFAULT_RATE_LIMIT_LIMIT=100      # Default requests per period
DEFAULT_RATE_LIMIT_PERIOD=3600    # Default period (1 hour)

# Redis Rate Limiter Settings  
REDIS_RATE_LIMITER_HOST=localhost
REDIS_RATE_LIMITER_PORT=6379
REDIS_RATE_LIMITER_DB=2           # Separate from cache/queue
```

### Creating User Tiers

```python
# Create tiers via API (superuser only)
POST /api/v1/tiers
{
    "name": "premium",
    "description": "Premium subscription with higher limits"
}

# Assign tier to user
PUT /api/v1/users/{user_id}/tier
{
    "tier_id": 2
}
```

### Setting Rate Limits

```python
# Create rate limits per tier and endpoint
POST /api/v1/tier/premium/rate_limit
{
    "name": "premium_posts_limit",
    "path": "/api/v1/posts",
    "limit": 100,        # 100 requests
    "period": 3600       # per hour
}

# Different limits for different endpoints
POST /api/v1/tier/free/rate_limit  
{
    "name": "free_ai_limit",
    "path": "/api/v1/ai/generate",
    "limit": 5,          # 5 requests  
    "period": 86400      # per day
}
```

## Usage Patterns

### Basic Protection

```python
# Protect all endpoints in a router
router = APIRouter(dependencies=[Depends(rate_limiter_dependency)])

@router.get("/users")
async def get_users():
    """Rate limited based on user tier."""
    pass

@router.post("/posts")  
async def create_post():
    """Rate limited based on user tier."""
    pass
```

### Selective Protection

```python
# Protect only specific endpoints
@router.get("/public-data")
async def get_public_data():
    """No rate limiting - public endpoint."""
    pass

@router.post("/premium-feature", dependencies=[Depends(rate_limiter_dependency)])
async def premium_feature():
    """Rate limited - premium feature."""
    pass
```

### Custom Error Handling

```python
from app.core.exceptions.http_exceptions import RateLimitException

@app.exception_handler(RateLimitException)
async def rate_limit_handler(request: Request, exc: RateLimitException):
    """Custom rate limit error response."""
    return JSONResponse(
        status_code=429,
        content={
            "error": "Rate limit exceeded",
            "message": "Too many requests. Please try again later.",
            "retry_after": 60  # Suggest retry time
        },
        headers={"Retry-After": "60"}
    )
```

## Monitoring and Analytics

### Rate Limit Metrics

```python
@router.get("/admin/rate-limit-stats")
async def get_rate_limit_stats():
    """Monitor rate limiting effectiveness."""
    
    # Get Redis statistics
    redis_info = await rate_limiter.client.info()
    
    # Count current rate limit keys
    pattern = "ratelimit:*"
    keys = await rate_limiter.client.keys(pattern)
    
    # Analyze by endpoint
    endpoint_stats = {}
    for key in keys:
        parts = key.split(":")
        if len(parts) >= 3:
            endpoint = parts[2]
            endpoint_stats[endpoint] = endpoint_stats.get(endpoint, 0) + 1
    
    return {
        "total_active_limits": len(keys),
        "redis_memory_usage": redis_info.get("used_memory_human"),
        "endpoint_stats": endpoint_stats
    }
```

### User Analytics

```python
async def analyze_user_usage(user_id: int, days: int = 7):
    """Analyze user's API usage patterns."""
    
    # This would require additional logging/analytics
    # implementation to track request patterns
    
    return {
        "user_id": user_id,
        "tier": "premium",
        "requests_last_7_days": 2540,
        "average_requests_per_day": 363,
        "top_endpoints": [
            {"path": "/api/v1/posts", "count": 1200},
            {"path": "/api/v1/users", "count": 800},
            {"path": "/api/v1/ai/generate", "count": 540}
        ],
        "rate_limit_hits": 12,  # Times user hit rate limits
        "suggested_tier": "enterprise"  # Based on usage patterns
    }
```

## Best Practices

### Rate Limit Design

```python
# Design limits based on resource cost
expensive_endpoints = {
    "/api/v1/ai/generate": {"limit": 10, "period": 3600},    # AI is expensive
    "/api/v1/reports/export": {"limit": 3, "period": 86400}, # Export is heavy
    "/api/v1/bulk/import": {"limit": 1, "period": 3600},     # Import is intensive
}

# More generous limits for lightweight endpoints  
lightweight_endpoints = {
    "/api/v1/users/me": {"limit": 1000, "period": 3600},     # Profile access
    "/api/v1/posts": {"limit": 300, "period": 3600},         # Content browsing
    "/api/v1/search": {"limit": 500, "period": 3600},        # Search queries
}
```

### Production Considerations

```python
# Use separate Redis database for rate limiting
REDIS_RATE_LIMITER_DB=2  # Isolate from cache and queues

# Set appropriate Redis memory policies
# maxmemory-policy volatile-lru  # Remove expired rate limit keys first

# Monitor Redis memory usage
# Rate limit keys can accumulate quickly under high load

# Consider rate limit key cleanup
async def cleanup_expired_rate_limits():
    """Clean up expired rate limit keys."""
    pattern = "ratelimit:*"
    keys = await redis_client.keys(pattern)
    
    for key in keys:
        ttl = await redis_client.ttl(key)
        if ttl == -2:  # Key expired but not cleaned up
            await redis_client.delete(key)
```

### Security Considerations

```python
# Rate limit by IP for unauthenticated users
if not user:
    user_id = request.client.host if request.client else "unknown"
    limit, period = DEFAULT_LIMIT, DEFAULT_PERIOD

# Prevent rate limit enumeration attacks
# Don't expose exact remaining requests in error messages

# Use progressive delays for repeated violations
# Consider temporary bans for severe abuse

# Log rate limit violations for security monitoring
if is_limited:
    logger.warning(
        f"Rate limit exceeded",
        extra={
            "user_id": user_id,
            "path": path,
            "ip": request.client.host if request.client else "unknown",
            "user_agent": request.headers.get("user-agent")
        }
    )
```

## Common Use Cases

### API Monetization

```python
# Different tiers for different pricing levels
tiers = {
    "free": {"daily_requests": 1000, "cost": 0},
    "starter": {"daily_requests": 10000, "cost": 29},
    "professional": {"daily_requests": 100000, "cost": 99},
    "enterprise": {"daily_requests": 1000000, "cost": 499}
}
```

### Resource Protection

```python
# Protect expensive operations
@router.post("/ai/generate-image", dependencies=[Depends(rate_limiter_dependency)])
async def generate_image():
    """Expensive AI operation - heavily rate limited."""
    pass

@router.get("/data/export", dependencies=[Depends(rate_limiter_dependency)])  
async def export_data():
    """Database-intensive operation - rate limited."""
    pass
```

### Abuse Prevention

```python
# Strict limits on user-generated content
@router.post("/posts", dependencies=[Depends(rate_limiter_dependency)])
async def create_post():
    """Prevent spam posting."""
    pass

@router.post("/comments", dependencies=[Depends(rate_limiter_dependency)])
async def create_comment():
    """Prevent comment spam.""" 
    pass
```

This comprehensive rate limiting system provides robust protection against API abuse while supporting flexible business models through user tiers and granular endpoint controls. 