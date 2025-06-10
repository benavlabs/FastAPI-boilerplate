# Client Cache

Client-side caching leverages HTTP cache headers to instruct browsers and CDNs to cache responses locally. This reduces server load and improves user experience by serving cached content directly from the client.

## Understanding Client Caching

Client caching works by setting HTTP headers that tell browsers, proxies, and CDNs how long they should cache responses. When implemented correctly, subsequent requests for the same resource are served instantly from the local cache.

### Benefits of Client Caching

**Reduced Latency**: Instant response from local cache eliminates network round trips  
**Lower Server Load**: Fewer requests reach your server infrastructure  
**Bandwidth Savings**: Cached responses don't consume network bandwidth  
**Better User Experience**: Faster page loads and improved responsiveness  
**Cost Reduction**: Lower server resource usage and bandwidth costs  

## Cache-Control Headers

The `Cache-Control` header is the primary mechanism for controlling client-side caching behavior.

### Header Components

```http
Cache-Control: public, max-age=3600, s-maxage=7200, must-revalidate
```

**Directive Breakdown:**

- **`public`**: Response can be cached by any cache (browsers, CDNs, proxies)
- **`private`**: Response can only be cached by browsers, not shared caches
- **`max-age=3600`**: Cache for 3600 seconds (1 hour) in browsers
- **`s-maxage=7200`**: Cache for 7200 seconds (2 hours) in shared caches (CDNs)
- **`must-revalidate`**: Must check with server when cache expires
- **`no-cache`**: Must revalidate with server before using cached response
- **`no-store`**: Must not store any part of the response

### Common Cache Patterns

```python
# Static assets (images, CSS, JS)
"Cache-Control: public, max-age=31536000, immutable"  # 1 year

# API data that changes rarely
"Cache-Control: public, max-age=3600"  # 1 hour

# User-specific data
"Cache-Control: private, max-age=1800"  # 30 minutes, browser only

# Real-time data
"Cache-Control: no-cache, must-revalidate"  # Always validate

# Sensitive data
"Cache-Control: no-store, no-cache, must-revalidate"  # Never cache
```

## Middleware Implementation

The boilerplate includes middleware that automatically adds cache headers to responses.

### ClientCacheMiddleware

```python
# middleware/client_cache_middleware.py
from fastapi import FastAPI, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

class ClientCacheMiddleware(BaseHTTPMiddleware):
    """Middleware to set Cache-Control headers for client-side caching."""
    
    def __init__(self, app: FastAPI, max_age: int = 60) -> None:
        super().__init__(app)
        self.max_age = max_age

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response: Response = await call_next(request)
        response.headers["Cache-Control"] = f"public, max-age={self.max_age}"
        return response
```

### Adding Middleware to Application

```python
# main.py
from fastapi import FastAPI
from app.middleware.client_cache_middleware import ClientCacheMiddleware

app = FastAPI()

# Add client caching middleware
app.add_middleware(
    ClientCacheMiddleware,
    max_age=300  # 5 minutes default cache
)
```

### Custom Middleware Configuration

```python
class AdvancedClientCacheMiddleware(BaseHTTPMiddleware):
    """Advanced client cache middleware with path-specific configurations."""
    
    def __init__(
        self, 
        app: FastAPI, 
        default_max_age: int = 300,
        path_configs: dict[str, dict] = None
    ):
        super().__init__(app)
        self.default_max_age = default_max_age
        self.path_configs = path_configs or {}
    
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        
        # Get path-specific configuration
        cache_config = self._get_cache_config(request.url.path)
        
        # Set cache headers based on configuration
        if cache_config.get("no_cache", False):
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        else:
            max_age = cache_config.get("max_age", self.default_max_age)
            visibility = "private" if cache_config.get("private", False) else "public"
            
            cache_control = f"{visibility}, max-age={max_age}"
            
            if cache_config.get("must_revalidate", False):
                cache_control += ", must-revalidate"
            
            if cache_config.get("immutable", False):
                cache_control += ", immutable"
                
            response.headers["Cache-Control"] = cache_control
        
        return response
    
    def _get_cache_config(self, path: str) -> dict:
        """Get cache configuration for a specific path."""
        for pattern, config in self.path_configs.items():
            if path.startswith(pattern):
                return config
        return {}

# Usage with path-specific configurations
app.add_middleware(
    AdvancedClientCacheMiddleware,
    default_max_age=300,
    path_configs={
        "/api/v1/static/": {"max_age": 31536000, "immutable": True},  # 1 year for static assets
        "/api/v1/auth/": {"no_cache": True},                          # No cache for auth endpoints
        "/api/v1/users/me": {"private": True, "max_age": 900},        # 15 min private cache for user data
        "/api/v1/public/": {"max_age": 1800},                         # 30 min for public data
    }
)
```

## Manual Cache Control

Set cache headers manually in specific endpoints for fine-grained control.

### Response Header Manipulation

```python
from fastapi import APIRouter, Response

router = APIRouter()

@router.get("/api/v1/static-data")
async def get_static_data(response: Response):
    """Endpoint with long-term caching for static data."""
    # Set cache headers for static data
    response.headers["Cache-Control"] = "public, max-age=86400, immutable"  # 24 hours
    response.headers["Last-Modified"] = "Wed, 21 Oct 2023 07:28:00 GMT"
    response.headers["ETag"] = '"abc123"'
    
    return {"data": "static content that rarely changes"}

@router.get("/api/v1/user-data")
async def get_user_data(response: Response, current_user: dict = Depends(get_current_user)):
    """Endpoint with private caching for user-specific data."""
    # Private cache for user-specific data
    response.headers["Cache-Control"] = "private, max-age=1800"  # 30 minutes
    response.headers["Vary"] = "Authorization"  # Cache varies by auth header
    
    return {"user_id": current_user["id"], "preferences": "user data"}

@router.get("/api/v1/real-time-data")
async def get_real_time_data(response: Response):
    """Endpoint that should not be cached."""
    # Prevent caching for real-time data
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    
    return {"timestamp": datetime.utcnow(), "live_data": "current status"}
```

### Conditional Caching

Implement conditional caching based on request parameters:

```python
@router.get("/api/v1/posts")
async def get_posts(
    response: Response,
    page: int = 1,
    per_page: int = 10,
    category: str = None
):
    """Conditional caching based on parameters."""
    
    # Different cache strategies based on parameters
    if category:
        # Category-specific data changes less frequently
        response.headers["Cache-Control"] = "public, max-age=1800"  # 30 minutes
    elif page == 1:
        # First page cached more aggressively
        response.headers["Cache-Control"] = "public, max-age=600"   # 10 minutes
    else:
        # Other pages cached for shorter duration
        response.headers["Cache-Control"] = "public, max-age=300"   # 5 minutes
    
    # Add ETag for efficient revalidation
    content_hash = hashlib.md5(f"{page}{per_page}{category}".encode()).hexdigest()
    response.headers["ETag"] = f'"{content_hash}"'
    
    posts = await crud_posts.get_multi(
        db=db,
        offset=(page - 1) * per_page,
        limit=per_page,
        category=category
    )
    
    return {"posts": posts, "page": page, "per_page": per_page}
```

## ETag Implementation

ETags enable efficient cache validation by allowing clients to check if content has changed.

### ETag Generation

```python
import hashlib
from typing import Any

def generate_etag(data: Any) -> str:
    """Generate ETag from data content."""
    content = json.dumps(data, sort_keys=True, default=str)
    return hashlib.md5(content.encode()).hexdigest()

@router.get("/api/v1/users/{user_id}")
async def get_user(
    request: Request,
    response: Response,
    user_id: int
):
    """Endpoint with ETag support for efficient caching."""
    
    user = await crud_users.get(db=db, id=user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Generate ETag from user data
    etag = generate_etag(user)
    
    # Check if client has current version
    if_none_match = request.headers.get("If-None-Match")
    if if_none_match == f'"{etag}"':
        # Content hasn't changed, return 304 Not Modified
        response.status_code = 304
        return Response(status_code=304)
    
    # Set ETag and cache headers
    response.headers["ETag"] = f'"{etag}"'
    response.headers["Cache-Control"] = "private, max-age=1800, must-revalidate"
    
    return user
```

### Last-Modified Headers

Use Last-Modified headers for time-based cache validation:

```python
@router.get("/api/v1/posts/{post_id}")
async def get_post(
    request: Request,
    response: Response,
    post_id: int
):
    """Endpoint with Last-Modified header support."""
    
    post = await crud_posts.get(db=db, id=post_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    
    # Use post's updated_at timestamp
    last_modified = post["updated_at"]
    
    # Check If-Modified-Since header
    if_modified_since = request.headers.get("If-Modified-Since")
    if if_modified_since:
        client_time = datetime.strptime(if_modified_since, "%a, %d %b %Y %H:%M:%S GMT")
        if last_modified <= client_time:
            response.status_code = 304
            return Response(status_code=304)
    
    # Set Last-Modified header
    response.headers["Last-Modified"] = last_modified.strftime("%a, %d %b %Y %H:%M:%S GMT")
    response.headers["Cache-Control"] = "public, max-age=3600, must-revalidate"
    
    return post
```

## Cache Strategy by Content Type

Different types of content require different caching strategies.

### Static Assets

```python
@router.get("/static/{file_path:path}")
async def serve_static(response: Response, file_path: str):
    """Serve static files with aggressive caching."""
    
    # Static assets can be cached for a long time
    response.headers["Cache-Control"] = "public, max-age=31536000, immutable"  # 1 year
    response.headers["Vary"] = "Accept-Encoding"  # Vary by compression
    
    # Add file-specific ETag based on file modification time
    file_stat = os.stat(f"static/{file_path}")
    etag = hashlib.md5(f"{file_path}{file_stat.st_mtime}".encode()).hexdigest()
    response.headers["ETag"] = f'"{etag}"'
    
    return FileResponse(f"static/{file_path}")
```

### API Responses

```python
# Reference data (rarely changes)
@router.get("/api/v1/countries")
async def get_countries(response: Response, db: AsyncSession = Depends(async_get_db)):
    response.headers["Cache-Control"] = "public, max-age=86400"  # 24 hours
    return await crud_countries.get_all(db=db)

# User-generated content (moderate changes)
@router.get("/api/v1/posts")
async def get_posts(response: Response, db: AsyncSession = Depends(async_get_db)):
    response.headers["Cache-Control"] = "public, max-age=1800"  # 30 minutes
    return await crud_posts.get_multi(db=db, is_deleted=False)

# Personal data (private caching only)
@router.get("/api/v1/users/me/notifications")
async def get_notifications(
    response: Response, 
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(async_get_db)
):
    response.headers["Cache-Control"] = "private, max-age=300"  # 5 minutes
    response.headers["Vary"] = "Authorization"
    return await crud_notifications.get_user_notifications(db=db, user_id=current_user["id"])

# Real-time data (no caching)
@router.get("/api/v1/system/status")
async def get_system_status(response: Response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return {"status": "online", "timestamp": datetime.utcnow()}
```

## Vary Header Usage

The `Vary` header tells caches which request headers affect the response, enabling proper cache key generation.

### Common Vary Patterns

```python
# Cache varies by authorization (user-specific content)
response.headers["Vary"] = "Authorization"

# Cache varies by accepted language
response.headers["Vary"] = "Accept-Language"

# Cache varies by compression support
response.headers["Vary"] = "Accept-Encoding"

# Multiple varying headers
response.headers["Vary"] = "Authorization, Accept-Language, Accept-Encoding"

# Example implementation
@router.get("/api/v1/dashboard")
async def get_dashboard(
    request: Request,
    response: Response,
    current_user: dict = Depends(get_current_user)
):
    """Dashboard content that varies by user and language."""
    
    # Content varies by user (Authorization) and language preference
    response.headers["Vary"] = "Authorization, Accept-Language"
    response.headers["Cache-Control"] = "private, max-age=900"  # 15 minutes
    
    language = request.headers.get("Accept-Language", "en")
    
    dashboard_data = await generate_dashboard(
        user_id=current_user["id"],
        language=language
    )
    
    return dashboard_data
```

## CDN Integration

Configure cache headers for optimal CDN performance.

### CDN-Specific Headers

```python
@router.get("/api/v1/public-content")
async def get_public_content(response: Response):
    """Content optimized for CDN caching."""
    
    # Different cache times for browser vs CDN
    response.headers["Cache-Control"] = "public, max-age=300, s-maxage=3600"  # 5 min browser, 1 hour CDN
    
    # CDN-specific headers (CloudFlare example)
    response.headers["CF-Cache-Tag"] = "public-content,api-v1"  # Cache tags for purging
    response.headers["CF-Edge-Cache"] = "max-age=86400"         # Edge cache for 24 hours
    
    return await get_public_content_data()
```

### Cache Purging

Implement cache purging for content updates:

```python
@router.put("/api/v1/posts/{post_id}")
async def update_post(
    response: Response,
    post_id: int,
    post_data: PostUpdate,
    current_user: dict = Depends(get_current_user)
):
    """Update post and invalidate related caches."""
    
    # Update the post
    updated_post = await crud_posts.update(db=db, id=post_id, object=post_data)
    
    # Set headers to indicate cache invalidation is needed
    response.headers["Cache-Control"] = "no-cache"
    response.headers["X-Cache-Purge"] = f"post-{post_id},user-{current_user['id']}-posts"
    
    # In production, trigger CDN purge here
    # await purge_cdn_cache([f"post-{post_id}", f"user-{current_user['id']}-posts"])
    
    return updated_post
```

## Best Practices

### Cache Duration Guidelines

```python
# Choose appropriate cache durations based on content characteristics:

# Static assets (CSS, JS, images with versioning)
max_age = 31536000  # 1 year

# API reference data (countries, categories)
max_age = 86400     # 24 hours

# User-generated content (posts, comments)
max_age = 1800      # 30 minutes

# User-specific data (profiles, preferences)
max_age = 900       # 15 minutes

# Search results
max_age = 600       # 10 minutes

# Real-time data (live scores, chat)
max_age = 0         # No caching
```

### Security Considerations

```python
# Never cache sensitive data
@router.get("/api/v1/admin/secrets")
async def get_secrets(response: Response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return {"secret": "sensitive_data"}

# Use private caching for user-specific content
@router.get("/api/v1/users/me/private-data")
async def get_private_data(response: Response):
    response.headers["Cache-Control"] = "private, max-age=300, must-revalidate"
    response.headers["Vary"] = "Authorization"
    return {"private": "user_data"}
```

Client-side caching, when properly implemented, provides significant performance improvements while maintaining security and data freshness through intelligent cache control strategies. 