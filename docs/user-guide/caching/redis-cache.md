# Redis Cache

Redis-based server-side caching provides fast, in-memory storage for API responses. The boilerplate includes a sophisticated caching decorator that automatically handles cache storage, retrieval, and invalidation.

## Understanding Redis Caching

Redis serves as a high-performance cache layer between your API and database. When properly implemented, it can reduce response times from hundreds of milliseconds to single-digit milliseconds by serving data directly from memory.

### Why Redis?

**Performance**: In-memory storage provides sub-millisecond data access
**Scalability**: Handles thousands of concurrent connections efficiently  
**Persistence**: Optional data persistence for cache warm-up after restarts
**Atomic Operations**: Thread-safe operations for concurrent applications
**Pattern Matching**: Advanced key pattern operations for bulk cache invalidation

## Cache Decorator

The `@cache` decorator provides a simple interface for adding caching to any FastAPI endpoint.

### Basic Usage

```python
from fastapi import APIRouter, Request
from app.core.utils.cache import cache

router = APIRouter()

@router.get("/posts/{post_id}")
@cache(key_prefix="post_cache", expiration=3600)
async def get_post(request: Request, post_id: int):
    # This function's result will be cached for 1 hour
    post = await crud_posts.get(db=db, id=post_id)
    return post
```

**How It Works:**

1. **Cache Check**: On GET requests, checks Redis for existing cached data
2. **Cache Miss**: If no cache exists, executes the function and stores the result
3. **Cache Hit**: Returns cached data directly, bypassing function execution
4. **Invalidation**: Automatically removes cache on non-GET requests (POST, PUT, DELETE)

### Decorator Parameters

```python
@cache(
    key_prefix: str,                                    # Cache key prefix
    resource_id_name: str = None,                       # Explicit resource ID parameter
    expiration: int = 3600,                             # Cache TTL in seconds
    resource_id_type: type | tuple[type, ...] = int,    # Expected ID type
    to_invalidate_extra: dict[str, str] = None,         # Additional keys to invalidate
    pattern_to_invalidate_extra: list[str] = None       # Pattern-based invalidation
)
```

#### Key Prefix

The key prefix creates unique cache identifiers:

```python
# Simple prefix
@cache(key_prefix="user_data")
# Generates keys like: "user_data:123"

# Dynamic prefix with placeholders
@cache(key_prefix="{username}_posts")  
# Generates keys like: "johndoe_posts:456"

# Complex prefix with multiple parameters
@cache(key_prefix="user_{user_id}_posts_page_{page}")
# Generates keys like: "user_123_posts_page_2:789"
```

#### Resource ID Handling

```python
# Automatic ID inference (looks for 'id' parameter)
@cache(key_prefix="post_cache")
async def get_post(request: Request, post_id: int):
    # Uses post_id automatically

# Explicit ID parameter
@cache(key_prefix="user_cache", resource_id_name="username")
async def get_user(request: Request, username: str):
    # Uses username instead of looking for 'id'

# Multiple ID types
@cache(key_prefix="search", resource_id_type=(int, str))
async def search(request: Request, query: str, page: int):
    # Accepts either string or int as resource ID
```

### Advanced Caching Patterns

#### Paginated Data Caching

```python
@router.get("/users/{username}/posts")
@cache(
    key_prefix="{username}_posts:page_{page}:items_per_page_{items_per_page}",
    resource_id_name="username",
    expiration=300  # 5 minutes for paginated data
)
async def get_user_posts(
    request: Request,
    username: str,
    page: int = 1,
    items_per_page: int = 10
):
    offset = compute_offset(page, items_per_page)
    posts = await crud_posts.get_multi(
        db=db,
        offset=offset,
        limit=items_per_page,
        created_by_user_id=user_id
    )
    return paginated_response(posts, page, items_per_page)
```

#### Hierarchical Data Caching

```python
@router.get("/organizations/{org_id}/departments/{dept_id}/employees")
@cache(
    key_prefix="org_{org_id}_dept_{dept_id}_employees",
    resource_id_name="dept_id",
    expiration=1800  # 30 minutes
)
async def get_department_employees(
    request: Request,
    org_id: int,
    dept_id: int
):
    employees = await crud_employees.get_multi(
        db=db,
        department_id=dept_id,
        organization_id=org_id
    )
    return employees
```

## Cache Invalidation

Cache invalidation ensures data consistency when the underlying data changes.

### Automatic Invalidation

The cache decorator automatically invalidates cache entries on non-GET requests:

```python
@router.put("/posts/{post_id}")
@cache(key_prefix="post_cache", resource_id_name="post_id")
async def update_post(request: Request, post_id: int, data: PostUpdate):
    # Automatically invalidates "post_cache:123" when called with PUT/POST/DELETE
    await crud_posts.update(db=db, id=post_id, object=data)
    return {"message": "Post updated"}
```

### Extra Key Invalidation

Invalidate related cache entries when data changes:

```python
@router.post("/posts")
@cache(
    key_prefix="new_post",
    resource_id_name="user_id", 
    to_invalidate_extra={
        "user_posts": "{user_id}",           # Invalidate user's post list
        "latest_posts": "global",            # Invalidate global latest posts
        "user_stats": "{user_id}"            # Invalidate user statistics
    }
)
async def create_post(request: Request, post: PostCreate, user_id: int):
    # Creating a post invalidates related cached data
    new_post = await crud_posts.create(db=db, object=post)
    return new_post
```

### Pattern-Based Invalidation

Use Redis pattern matching for bulk invalidation:

```python
@router.put("/users/{user_id}/profile")
@cache(
    key_prefix="user_profile",
    resource_id_name="user_id",
    pattern_to_invalidate_extra=[
        "user_{user_id}_*",          # All user-related caches
        "*_user_{user_id}_*",        # Caches that include this user
        "search_results_*"           # All search result caches
    ]
)
async def update_user_profile(request: Request, user_id: int, data: UserUpdate):
    # Invalidates all matching cache patterns
    await crud_users.update(db=db, id=user_id, object=data)
    return {"message": "Profile updated"}
```

**Pattern Examples:**

- `user_*` - All keys starting with "user_"
- `*_posts` - All keys ending with "_posts"  
- `user_*_posts_*` - Complex patterns with wildcards
- `temp_*` - Temporary cache entries

## Configuration

### Redis Settings

Configure Redis connection in your environment settings:

```python
# core/config.py
class RedisCacheSettings(BaseSettings):
    REDIS_CACHE_HOST: str = config("REDIS_CACHE_HOST", default="localhost")
    REDIS_CACHE_PORT: int = config("REDIS_CACHE_PORT", default=6379) 
    REDIS_CACHE_PASSWORD: str = config("REDIS_CACHE_PASSWORD", default="")
    REDIS_CACHE_DB: int = config("REDIS_CACHE_DB", default=0)
    REDIS_CACHE_URL: str = f"redis://:{REDIS_CACHE_PASSWORD}@{REDIS_CACHE_HOST}:{REDIS_CACHE_PORT}/{REDIS_CACHE_DB}"
```

### Environment Variables

```bash
# Basic Configuration
REDIS_CACHE_HOST=localhost
REDIS_CACHE_PORT=6379

# Production Configuration  
REDIS_CACHE_HOST=redis.production.com
REDIS_CACHE_PORT=6379
REDIS_CACHE_PASSWORD=your-secure-password
REDIS_CACHE_DB=0

# Docker Compose
REDIS_CACHE_HOST=redis
REDIS_CACHE_PORT=6379
```

### Connection Pool Setup

The boilerplate automatically configures Redis connection pooling:

```python
# core/setup.py
async def create_redis_cache_pool() -> None:
    """Initialize Redis connection pool for caching."""
    cache.pool = redis.ConnectionPool.from_url(
        settings.REDIS_CACHE_URL,
        max_connections=20,      # Maximum connections in pool
        retry_on_timeout=True,   # Retry on connection timeout
        socket_timeout=5.0,      # Socket timeout in seconds
        health_check_interval=30 # Health check frequency
    )
    cache.client = redis.Redis.from_pool(cache.pool)
```

### Cache Client Usage

Direct Redis client access for custom caching logic:

```python
from app.core.utils.cache import client

async def custom_cache_operation():
    if client is None:
        raise MissingClientError("Redis client not initialized")
    
    # Set custom cache entry
    await client.set("custom_key", "custom_value", ex=3600)
    
    # Get cached value
    cached_value = await client.get("custom_key")
    
    # Delete cache entry
    await client.delete("custom_key")
    
    # Bulk operations
    pipe = client.pipeline()
    pipe.set("key1", "value1")
    pipe.set("key2", "value2") 
    pipe.expire("key1", 3600)
    await pipe.execute()
```

## Performance Optimization

### Connection Pooling

Connection pooling prevents the overhead of creating new Redis connections for each request:

```python
# Benefits of connection pooling:
# - Reuses existing connections
# - Handles connection failures gracefully
# - Provides connection health checks
# - Supports concurrent operations

# Pool configuration
redis.ConnectionPool.from_url(
    settings.REDIS_CACHE_URL,
    max_connections=20,        # Adjust based on expected load
    retry_on_timeout=True,     # Handle network issues
    socket_keepalive=True,     # Keep connections alive
    socket_keepalive_options={}
)
```

### Cache Key Generation

The cache decorator automatically generates keys using this pattern:

```python
# Decorator generates: "{formatted_key_prefix}:{resource_id}"
@cache(key_prefix="post_cache", resource_id_name="post_id")
# Generates: "post_cache:123"

@cache(key_prefix="{username}_posts:page_{page}")
# Generates: "johndoe_posts:page_1:456" (where 456 is the resource_id)

# The system handles key formatting automatically - you just provide the prefix template
```

**What you control:**
- `key_prefix` template with placeholders like `{username}`, `{page}`
- `resource_id_name` to specify which parameter to use as the ID
- The decorator handles the rest

**Generated key examples from the boilerplate:**
```python
# From posts.py
"{username}_posts:page_{page}:items_per_page_{items_per_page}" → "john_posts:page_1:items_per_page_10:789"
"{username}_post_cache" → "john_post_cache:123"
```

### Expiration Strategies

Choose appropriate expiration times based on data characteristics:

```python
# Static reference data (rarely changes)
@cache(key_prefix="countries", expiration=86400)  # 24 hours

# User-generated content (changes moderately)
@cache(key_prefix="user_posts", expiration=1800)  # 30 minutes

# Real-time data (changes frequently)
@cache(key_prefix="live_stats", expiration=60)    # 1 minute

# Search results (can be stale)
@cache(key_prefix="search", expiration=3600)      # 1 hour
```

This comprehensive Redis caching system provides high-performance data access while maintaining data consistency through intelligent invalidation strategies. 