# API Versioning

Learn how to version your APIs properly using the boilerplate's built-in versioning structure and best practices for maintaining backward compatibility.

## Quick Start

The boilerplate is already set up for versioning with a `v1` structure:

```text
src/app/api/
├── dependencies.py          # Shared across all versions
└── v1/                     # Version 1 of your API
    ├── __init__.py         # Router registration
    ├── users.py           # User endpoints
    ├── posts.py           # Post endpoints
    └── ...                # Other endpoints
```

Your endpoints are automatically available at `/api/v1/...`:

- `GET /api/v1/users/` - Get users
- `POST /api/v1/users/` - Create user
- `GET /api/v1/posts/` - Get posts

## Current Structure

### Version 1 (v1)

The current API version is in `src/app/api/v1/`:

```python
# src/app/api/v1/__init__.py
from fastapi import APIRouter

from .users import router as users_router
from .posts import router as posts_router
from .login import router as login_router

# Main v1 router
api_router = APIRouter()

# Include all v1 endpoints
api_router.include_router(users_router)
api_router.include_router(posts_router)
api_router.include_router(login_router)
```

### Main App Registration

In `src/app/main.py`, v1 is registered:

```python
from fastapi import FastAPI
from app.api.v1 import api_router as api_v1_router

app = FastAPI()

# Register v1 API
app.include_router(api_v1_router, prefix="/api/v1")
```

## Adding Version 2

When you need to make breaking changes, create a new version:

### Step 1: Create v2 Directory

```text
src/app/api/
├── dependencies.py
├── v1/                     # Keep v1 unchanged
│   ├── __init__.py
│   ├── users.py
│   └── ...
└── v2/                     # New version
    ├── __init__.py
    ├── users.py           # Updated user endpoints
    └── ...
```

### Step 2: Create v2 Router

```python
# src/app/api/v2/__init__.py
from fastapi import APIRouter

from .users import router as users_router
# Import other v2 routers

# Main v2 router
api_router = APIRouter()

# Include v2 endpoints
api_router.include_router(users_router)
```

### Step 3: Register v2 in Main App

```python
# src/app/main.py
from fastapi import FastAPI
from app.api.v1 import api_router as api_v1_router
from app.api.v2 import api_router as api_v2_router

app = FastAPI()

# Register both versions
app.include_router(api_v1_router, prefix="/api/v1")
app.include_router(api_v2_router, prefix="/api/v2")
```

## Version 2 Example

Here's how you might evolve the user endpoints in v2:

### v1 User Endpoint
```python
# src/app/api/v1/users.py
from app.schemas.user import UserRead, UserCreate

@router.get("/", response_model=list[UserRead])
async def get_users():
    users = await crud_users.get_multi(db=db, schema_to_select=UserRead)
    return users["data"]

@router.post("/", response_model=UserRead)
async def create_user(user_data: UserCreate):
    return await crud_users.create(db=db, object=user_data)
```

### v2 User Endpoint (with breaking changes)
```python
# src/app/api/v2/users.py
from app.schemas.user import UserReadV2, UserCreateV2  # New schemas
from fastcrud.paginated import PaginatedListResponse

# Breaking change: Always return paginated response
@router.get("/", response_model=PaginatedListResponse[UserReadV2])
async def get_users(page: int = 1, items_per_page: int = 10):
    users = await crud_users.get_multi(
        db=db,
        offset=(page - 1) * items_per_page,
        limit=items_per_page,
        schema_to_select=UserReadV2
    )
    return paginated_response(users, page, items_per_page)

# Breaking change: Require authentication
@router.post("/", response_model=UserReadV2)
async def create_user(
    user_data: UserCreateV2,
    current_user: Annotated[dict, Depends(get_current_user)]  # Now required
):
    return await crud_users.create(db=db, object=user_data)
```

## Schema Versioning

Create separate schemas for different versions:

### Version 1 Schema
```python
# src/app/schemas/user.py (existing)
class UserRead(BaseModel):
    id: int
    name: str
    username: str
    email: str
    profile_image_url: str
    tier_id: int | None

class UserCreate(BaseModel):
    name: str
    username: str
    email: str
    password: str
```

### Version 2 Schema (with changes)
```python
# src/app/schemas/user_v2.py (new file)
from datetime import datetime

class UserReadV2(BaseModel):
    id: int
    name: str
    username: str
    email: str
    avatar_url: str          # Changed from profile_image_url
    subscription_tier: str   # Changed from tier_id to string
    created_at: datetime     # New field
    is_verified: bool        # New field

class UserCreateV2(BaseModel):
    name: str
    username: str
    email: str
    password: str
    accept_terms: bool       # New required field
```

## Gradual Migration Strategy

### 1. Keep Both Versions Running

```python
# Both versions work simultaneously
# v1: GET /api/v1/users/ -> list[UserRead]
# v2: GET /api/v2/users/ -> PaginatedListResponse[UserReadV2]
```

### 2. Add Deprecation Warnings

```python
# src/app/api/v1/users.py
import warnings
from fastapi import HTTPException

@router.get("/", response_model=list[UserRead])
async def get_users(response: Response):
    # Add deprecation header
    response.headers["X-API-Deprecation"] = "v1 is deprecated. Use v2."
    response.headers["X-API-Sunset"] = "2024-12-31"  # When v1 will be removed
    
    users = await crud_users.get_multi(db=db, schema_to_select=UserRead)
    return users["data"]
```

### 3. Monitor Usage

Track which versions are being used:

```python
# src/app/api/middleware.py
from fastapi import Request
import logging

logger = logging.getLogger(__name__)

async def version_tracking_middleware(request: Request, call_next):
    if request.url.path.startswith("/api/v1/"):
        logger.info(f"v1 usage: {request.method} {request.url.path}")
    elif request.url.path.startswith("/api/v2/"):
        logger.info(f"v2 usage: {request.method} {request.url.path}")
    
    response = await call_next(request)
    return response
```

## Shared Code Between Versions

Keep common logic in shared modules:

### Shared Dependencies
```python
# src/app/api/dependencies.py - shared across all versions
async def get_current_user(...):
    # Authentication logic used by all versions
    pass

async def get_db():
    # Database connection used by all versions
    pass
```

### Shared CRUD Operations
```python
# The CRUD layer can be shared between versions
# Only the schemas and endpoints change

# v1 endpoint
@router.get("/", response_model=list[UserRead])
async def get_users_v1():
    users = await crud_users.get_multi(schema_to_select=UserRead)
    return users["data"]

# v2 endpoint  
@router.get("/", response_model=PaginatedListResponse[UserReadV2])
async def get_users_v2():
    users = await crud_users.get_multi(schema_to_select=UserReadV2)
    return paginated_response(users, page, items_per_page)
```

## Version Discovery

Let clients discover available versions:

```python
# src/app/api/versions.py
from fastapi import APIRouter

router = APIRouter()

@router.get("/versions")
async def get_api_versions():
    return {
        "available_versions": ["v1", "v2"],
        "current_version": "v2",
        "deprecated_versions": [],
        "sunset_dates": {
            "v1": "2024-12-31"
        }
    }
```

Register it in main.py:
```python
# src/app/main.py
from app.api.versions import router as versions_router

app.include_router(versions_router, prefix="/api")
# Now available at GET /api/versions
```

## Testing Multiple Versions

Test both versions to ensure compatibility:

```python
# tests/test_api_versioning.py
import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_v1_users(client: AsyncClient):
    """Test v1 returns simple list"""
    response = await client.get("/api/v1/users/")
    assert response.status_code == 200
    
    data = response.json()
    assert isinstance(data, list)  # v1 returns list

@pytest.mark.asyncio  
async def test_v2_users(client: AsyncClient):
    """Test v2 returns paginated response"""
    response = await client.get("/api/v2/users/")
    assert response.status_code == 200
    
    data = response.json()
    assert "data" in data  # v2 returns paginated response
    assert "total_count" in data
    assert "page" in data
```

## OpenAPI Documentation

Each version gets its own docs:

```python
# src/app/main.py
from fastapi import FastAPI

# Create separate apps for documentation
v1_app = FastAPI(title="My API v1", version="1.0.0")
v2_app = FastAPI(title="My API v2", version="2.0.0")

# Register routes
v1_app.include_router(api_v1_router)
v2_app.include_router(api_v2_router)

# Mount as sub-applications
main_app = FastAPI()
main_app.mount("/api/v1", v1_app)
main_app.mount("/api/v2", v2_app)
```

Now you have separate documentation:
- `/api/v1/docs` - v1 documentation
- `/api/v2/docs` - v2 documentation

## Best Practices

### 1. Semantic Versioning

- **v1.0** → **v1.1**: New features (backward compatible)
- **v1.1** → **v2.0**: Breaking changes (new version)

### 2. Clear Migration Path

```python
# Document what changed in v2
"""
API v2 Changes:
- GET /users/ now returns paginated response instead of array
- POST /users/ now requires authentication
- UserRead.profile_image_url renamed to avatar_url
- UserRead.tier_id changed to subscription_tier (string)
- Added UserRead.created_at and is_verified fields
- UserCreate now requires accept_terms field
"""
```

### 3. Gradual Deprecation

1. Release v2 alongside v1
2. Add deprecation warnings to v1
3. Set sunset date for v1
4. Monitor v1 usage
5. Remove v1 after sunset date

### 4. Consistent Patterns

Keep the same patterns across versions:

- Same URL structure: `/api/v{number}/resource`
- Same HTTP methods and status codes
- Same authentication approach
- Same error response format

## What's Next

Now that you understand API versioning:

- **[Database Migrations](../database/migrations.md)** - Handle database schema changes
- **[Testing](../testing.md)** - Test multiple API versions
- **[Production](../production.md)** - Deploy versioned APIs

Proper versioning lets you evolve your API without breaking existing clients!