# API Endpoints

This guide shows you how to create API endpoints using the boilerplate's established patterns. You'll learn the common patterns you need for building CRUD APIs.

## Quick Start

Here's how to create a typical endpoint using the boilerplate's patterns:

```python
from fastapi import APIRouter, Depends, HTTPException
from typing import Annotated

from app.core.db.database import async_get_db
from app.crud.crud_users import crud_users
from app.schemas.user import UserRead, UserCreate
from app.api.dependencies import get_current_user

router = APIRouter(prefix="/users", tags=["users"])

@router.get("/{user_id}", response_model=UserRead)
async def get_user(
    user_id: int,
    db: Annotated[AsyncSession, Depends(async_get_db)]
):
    """Get a user by ID."""
    user = await crud_users.get(db=db, id=user_id, schema_to_select=UserRead)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user
```

That's it! The boilerplate handles the rest.

## Common Endpoint Patterns

### 1. Get Single Item

```python
@router.get("/{user_id}", response_model=UserRead)
async def get_user(
    user_id: int,
    db: Annotated[AsyncSession, Depends(async_get_db)]
):
    user = await crud_users.get(db=db, id=user_id, schema_to_select=UserRead)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user
```

### 2. Get Multiple Items (with Pagination)

```python
from fastcrud.paginated import PaginatedListResponse

@router.get("/", response_model=PaginatedListResponse[UserRead])
async def get_users(
    page: int = 1,
    items_per_page: int = 10,
    db: Annotated[AsyncSession, Depends(async_get_db)]
):
    users = await crud_users.get_multi(
        db=db,
        offset=(page - 1) * items_per_page,
        limit=items_per_page,
        schema_to_select=UserRead,
        return_as_model=True,
        return_total_count=True
    )
    
    return paginated_response(
        crud_data=users,
        page=page, 
        items_per_page=items_per_page
    )
```

### 3. Create Item

```python
@router.post("/", response_model=UserRead, status_code=201)
async def create_user(
    user_data: UserCreate,
    db: Annotated[AsyncSession, Depends(async_get_db)]
):
    # Check if user already exists
    if await crud_users.exists(db=db, email=user_data.email):
        raise HTTPException(status_code=409, detail="Email already exists")
    
    # Create user
    new_user = await crud_users.create(db=db, object=user_data)
    return new_user
```

### 4. Update Item

```python
@router.patch("/{user_id}", response_model=UserRead)
async def update_user(
    user_id: int,
    user_data: UserUpdate,
    db: Annotated[AsyncSession, Depends(async_get_db)]
):
    # Check if user exists
    if not await crud_users.exists(db=db, id=user_id):
        raise HTTPException(status_code=404, detail="User not found")
    
    # Update user
    updated_user = await crud_users.update(db=db, object=user_data, id=user_id)
    return updated_user
```

### 5. Delete Item (Soft Delete)

```python
@router.delete("/{user_id}")
async def delete_user(
    user_id: int,
    db: Annotated[AsyncSession, Depends(async_get_db)]
):
    if not await crud_users.exists(db=db, id=user_id):
        raise HTTPException(status_code=404, detail="User not found")
    
    await crud_users.delete(db=db, id=user_id)
    return {"message": "User deleted"}
```

## Adding Authentication

To require login, add the `get_current_user` dependency:

```python
@router.get("/me", response_model=UserRead)  
async def get_my_profile(
    current_user: Annotated[dict, Depends(get_current_user)]
):
    """Get current user's profile."""
    return current_user

@router.post("/", response_model=UserRead)
async def create_user(
    user_data: UserCreate,
    current_user: Annotated[dict, Depends(get_current_user)],  # Requires login
    db: Annotated[AsyncSession, Depends(async_get_db)]
):
    # Only logged-in users can create users
    new_user = await crud_users.create(db=db, object=user_data)
    return new_user
```

## Adding Admin-Only Endpoints

For admin-only endpoints, use `get_current_superuser`:

```python
from app.api.dependencies import get_current_superuser

@router.delete("/{user_id}/permanent", dependencies=[Depends(get_current_superuser)])
async def permanently_delete_user(
    user_id: int,
    db: Annotated[AsyncSession, Depends(async_get_db)]
):
    """Admin-only: Permanently delete user from database."""
    await crud_users.db_delete(db=db, id=user_id)
    return {"message": "User permanently deleted"}
```

## Query Parameters

### Simple Parameters

```python
@router.get("/search")
async def search_users(
    name: str | None = None,        # Optional string
    age: int | None = None,         # Optional integer  
    is_active: bool = True,         # Boolean with default
    db: Annotated[AsyncSession, Depends(async_get_db)]
):
    filters = {"is_active": is_active}
    if name:
        filters["name"] = name
    if age:
        filters["age"] = age
        
    users = await crud_users.get_multi(db=db, **filters)
    return users["data"]
```

### Parameters with Validation

```python
from fastapi import Query

@router.get("/")
async def get_users(
    page: Annotated[int, Query(ge=1)] = 1,                    # Must be >= 1
    limit: Annotated[int, Query(ge=1, le=100)] = 10,          # Between 1-100
    search: Annotated[str | None, Query(max_length=50)] = None, # Max 50 chars
    db: Annotated[AsyncSession, Depends(async_get_db)]
):
    # Use the validated parameters
    users = await crud_users.get_multi(
        db=db,
        offset=(page - 1) * limit,
        limit=limit
    )
    return users["data"]
```

## Error Handling

The boilerplate includes custom exceptions you can use:

```python
from app.core.exceptions.http_exceptions import (
    NotFoundException, 
    DuplicateValueException,
    ForbiddenException
)

@router.get("/{user_id}")
async def get_user(user_id: int, db: AsyncSession):
    user = await crud_users.get(db=db, id=user_id)
    if not user:
        raise NotFoundException("User not found")  # Returns 404
    return user

@router.post("/")
async def create_user(user_data: UserCreate, db: AsyncSession):
    if await crud_users.exists(db=db, email=user_data.email):
        raise DuplicateValueException("Email already exists")  # Returns 409
    
    return await crud_users.create(db=db, object=user_data)
```

## File Uploads

```python
from fastapi import UploadFile, File

@router.post("/{user_id}/avatar")
async def upload_avatar(
    user_id: int,
    file: UploadFile = File(...),
    current_user: Annotated[dict, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(async_get_db)]
):
    # Check file type
    if not file.content_type.startswith('image/'):
        raise HTTPException(status_code=400, detail="File must be an image")
    
    # Save file and update user
    # ... file handling logic ...
    
    return {"message": "Avatar uploaded successfully"}
```

## Creating New Endpoints

### Step 1: Create the Router File

Create `src/app/api/v1/posts.py`:

```python
from fastapi import APIRouter, Depends, HTTPException
from typing import Annotated

from app.core.db.database import async_get_db
from app.crud.crud_posts import crud_posts  # You'll create this
from app.schemas.post import PostRead, PostCreate, PostUpdate  # You'll create these
from app.api.dependencies import get_current_user

router = APIRouter(prefix="/posts", tags=["posts"])

@router.get("/", response_model=list[PostRead])
async def get_posts(db: Annotated[AsyncSession, Depends(async_get_db)]):
    posts = await crud_posts.get_multi(db=db, schema_to_select=PostRead)
    return posts["data"]

@router.post("/", response_model=PostRead, status_code=201)
async def create_post(
    post_data: PostCreate,
    current_user: Annotated[dict, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(async_get_db)]
):
    # Add current user as post author
    post_dict = post_data.model_dump()
    post_dict["author_id"] = current_user["id"]
    
    new_post = await crud_posts.create(db=db, object=post_dict)
    return new_post
```

### Step 2: Register the Router

In `src/app/api/v1/__init__.py`, add:

```python
from .posts import router as posts_router

api_router.include_router(posts_router)
```

### Step 3: Test Your Endpoints

Your new endpoints will be available at:
- `GET /api/v1/posts/` - Get all posts
- `POST /api/v1/posts/` - Create new post (requires login)

## Best Practices

1. **Always use the database dependency**: `Depends(async_get_db)`
2. **Use existing CRUD methods**: `crud_users.get()`, `crud_users.create()`, etc.
3. **Check if items exist before operations**: Use `crud_users.exists()`
4. **Use proper HTTP status codes**: `status_code=201` for creation
5. **Add authentication when needed**: `Depends(get_current_user)`
6. **Use response models**: `response_model=UserRead`
7. **Handle errors with custom exceptions**: `NotFoundException`, `DuplicateValueException`

## What's Next

Now that you understand basic endpoints:

- **[Pagination](pagination.md)** - Add pagination to your endpoints
- **[Database Schemas](../database/schemas.md)** - Create schemas for your data
- **[CRUD Operations](../database/crud.md)** - Understand the CRUD layer

The boilerplate provides everything you need - just follow these patterns! 