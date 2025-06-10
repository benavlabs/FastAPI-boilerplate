# API Development

Learn how to build REST APIs with the FastAPI Boilerplate. This section covers everything you need to create robust, production-ready APIs.

## What You'll Learn

- **[Endpoints](endpoints.md)** - Create CRUD endpoints with authentication and validation
- **[Pagination](pagination.md)** - Add pagination to handle large datasets
- **[Exception Handling](exceptions.md)** - Handle errors properly with built-in exceptions
- **[API Versioning](versioning.md)** - Version your APIs and maintain backward compatibility
- **Database Integration** - Use the boilerplate's CRUD layer and schemas

## Quick Overview

The boilerplate provides everything you need for API development:

```python
from fastapi import APIRouter, Depends
from app.crud.crud_users import crud_users
from app.schemas.user import UserRead, UserCreate
from app.core.db.database import async_get_db

router = APIRouter(prefix="/users", tags=["users"])

@router.get("/", response_model=list[UserRead])
async def get_users(db: Annotated[AsyncSession, Depends(async_get_db)]):
    users = await crud_users.get_multi(db=db, schema_to_select=UserRead)
    return users["data"]

@router.post("/", response_model=UserRead, status_code=201)
async def create_user(
    user_data: UserCreate,
    db: Annotated[AsyncSession, Depends(async_get_db)]
):
    return await crud_users.create(db=db, object=user_data)
```

## Key Features

### 🔐 **Built-in Authentication**
Add authentication to any endpoint:
```python
from app.api.dependencies import get_current_user

@router.get("/me", response_model=UserRead)
async def get_profile(current_user: Annotated[dict, Depends(get_current_user)]):
    return current_user
```

### 📊 **Easy Pagination**
Paginate any endpoint with one line:
```python
from fastcrud.paginated import PaginatedListResponse

@router.get("/", response_model=PaginatedListResponse[UserRead])
async def get_users(page: int = 1, items_per_page: int = 10):
    # Add pagination to any endpoint
```

### ✅ **Automatic Validation**
Request and response validation is handled automatically:
```python
@router.post("/", response_model=UserRead)
async def create_user(user_data: UserCreate):  # ← Validates input
    return await crud_users.create(object=user_data)  # ← Validates output
```

### 🛡️ **Error Handling**
Use built-in exceptions for consistent error responses:
```python
from app.core.exceptions.http_exceptions import NotFoundException

@router.get("/{user_id}")
async def get_user(user_id: int):
    user = await crud_users.get(id=user_id)
    if not user:
        raise NotFoundException("User not found")  # Returns proper 404
    return user
```

## Architecture

The boilerplate follows a layered architecture:

```
API Endpoint
    ↓
Pydantic Schema (validation)
    ↓
CRUD Layer (database operations)
    ↓
SQLAlchemy Model (database)
```

This separation makes your code:
- **Testable** - Mock any layer easily
- **Maintainable** - Clear separation of concerns  
- **Scalable** - Add features without breaking existing code

## Directory Structure

```text
src/app/api/
├── dependencies.py          # Shared dependencies (auth, rate limiting)
└── v1/                     # API version 1
    ├── users.py           # User endpoints
    ├── posts.py           # Post endpoints
    ├── login.py           # Authentication
    └── ...                # Other endpoints
```

## What's Next

Start with the basics:

1. **[Endpoints](endpoints.md)** - Learn the common patterns for creating API endpoints
2. **[Pagination](pagination.md)** - Add pagination to handle large datasets
3. **[Exception Handling](exceptions.md)** - Handle errors properly with built-in exceptions
4. **[API Versioning](versioning.md)** - Version your APIs and maintain backward compatibility

Then dive deeper into the foundation:
5. **[Database Schemas](../database/schemas.md)** - Create schemas for your data
6. **[CRUD Operations](../database/crud.md)** - Understand the database layer

Each guide builds on the previous one with practical examples you can use immediately. 