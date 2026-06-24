# API Development

Learn how to build REST APIs with the FastAPI Boilerplate. This section covers everything you need to create robust, production-ready APIs.

## What You'll Learn

- **[Endpoints](endpoints.md)** - Create endpoints with authentication and validation
- **[Pagination](pagination.md)** - Add pagination to list endpoints
- **[Exception Handling](exceptions.md)** - Handle errors with the boilerplate's exception types
- **[API Versioning](versioning.md)** - Version your APIs and maintain backward compatibility

## Quick Overview

Routes are defined in each module's `routes.py`. The aggregator at `interfaces/api/v1/__init__.py` mounts each module's router under `/api/v1`.

```python
# backend/src/modules/user/routes.py
from typing import Annotated, Any
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.database.session import async_session
from .schemas import UserCreate, UserRead
from .service import UserService

router = APIRouter(tags=["Users"])


def get_user_service() -> UserService:
    return UserService()


@router.post("/", response_model=UserRead, status_code=201)
async def create_user(
    user: UserCreate,
    db: Annotated[AsyncSession, Depends(async_session)],
    user_service: Annotated[UserService, Depends(get_user_service)],
) -> dict[str, Any]:
    return await user_service.create(user, db)
```

The aggregator wires it up:

```python
# backend/src/interfaces/api/v1/__init__.py
from fastapi import APIRouter

from ....modules.user.routes import router as users_router

router = APIRouter(prefix="/v1")
router.include_router(users_router, prefix="/users")
```

Final URL: `POST /api/v1/users/`.

## Key Features

### Built-in Authentication

Session-based auth with HTTP-only cookies. Pull the current user from `infrastructure/auth/dependencies`:

```python
from ...infrastructure.auth.dependencies import get_current_user

@router.get("/me", response_model=UserRead)
async def get_profile(
    current_user: Annotated[dict[str, Any], Depends(get_current_user)],
) -> dict[str, Any]:
    return current_user
```

For superuser-only endpoints, swap in `get_current_superuser`. See [Authentication](../authentication/index.md) for the full picture.

### Easy Pagination

The boilerplate uses FastCRUD's `PaginatedListResponse` and `paginated_response()` helper:

```python
from fastcrud import PaginatedListResponse, compute_offset, paginated_response

@router.get("/", response_model=PaginatedListResponse[UserRead])
async def list_users(
    db: Annotated[AsyncSession, Depends(async_session)],
    user_service: Annotated[UserService, Depends(get_user_service)],
    page: int = 1,
    items_per_page: int = 10,
) -> dict[str, Any]:
    result = await user_service.get_paginated(
        skip=compute_offset(page, items_per_page),
        limit=items_per_page,
        db=db,
    )
    return paginated_response(crud_data=result, page=page, items_per_page=items_per_page)
```

### Automatic Validation

Request bodies, query parameters, and response models are all validated by Pydantic:

```python
@router.post("/", response_model=UserRead)
async def create_user(user: UserCreate):  # ← validates input
    return await user_service.create(user, db)  # ← validates output via response_model
```

### Error Handling

Domain errors live in `modules/common/exceptions.py`. Routes catch them and translate them to HTTP responses via `handle_exception`:

```python
from ...infrastructure.auth.http_exceptions import HTTPException
from ..common.utils.error_handler import handle_exception

@router.get("/{username}", response_model=UserRead)
async def get_user_by_username(
    username: str,
    db: Annotated[AsyncSession, Depends(async_session)],
    user_service: Annotated[UserService, Depends(get_user_service)],
) -> dict[str, Any]:
    try:
        user = await user_service.get_by_username(username, db)
        if user is None:
            raise HTTPException(status_code=404, detail=f"User with username {username} not found")
        return user
    except Exception as e:
        http_exception = handle_exception(e)
        if http_exception:
            raise http_exception
        raise HTTPException(status_code=500, detail="An unexpected error occurred")
```

See [Exception Handling](exceptions.md) for the full catalog.

## Architecture

```text
HTTP Request
    ↓
APIRouter         (modules/<feature>/routes.py)
    ↓
Service           (modules/<feature>/service.py)  — business rules, permission checks
    ↓
FastCRUD          (modules/<feature>/crud.py)
    ↓
SQLAlchemy Model  (modules/<feature>/models.py)
    ↓
PostgreSQL
```

The split keeps:

- HTTP concerns (status codes, schemas, dependencies) in `routes.py`
- Business logic (validation, orchestration) in `service.py`
- Database I/O in `crud.py`

You can mock any layer in tests; you can change one without breaking the others.

## Directory Structure

```text
backend/src/
├── interfaces/
│   └── api/
│       ├── __init__.py            # mounts /api
│       └── v1/
│           └── __init__.py        # mounts /v1 + every module's router
├── infrastructure/
│   └── auth/
│       └── routes.py              # /api/v1/auth/* (login, OAuth, check-auth)
└── modules/
    ├── user/routes.py             # /api/v1/users/*
    ├── tier/routes.py             # /api/v1/tiers/*
    ├── rate_limit/routes.py       # /api/v1/rate-limits/*
    └── api_keys/routes.py         # /api/v1/api-keys/*
```

Auth lives in `infrastructure/auth/routes.py` instead of in a feature module because authentication is structural — every other feature depends on it.

## Mounted Endpoints

What ships out of the box (40 total routes):

| Prefix | Source | Notes |
|--------|--------|-------|
| `POST/GET/PATCH/DELETE /api/v1/users/*` | `modules/user/routes.py` | Open create, session/superuser-gated reads/updates |
| `GET /api/v1/tiers/*` | `modules/tier/routes.py` | Public list + lookup by name |
| `GET/PATCH/DELETE /api/v1/rate-limits/*` | `modules/rate_limit/routes.py` | List/get public; PATCH/DELETE require superuser |
| `POST /api/v1/auth/login`, `logout`, `refresh-csrf`, `check-auth` | `infrastructure/auth/routes.py` | Session auth |
| `GET /api/v1/auth/oauth/google`, `oauth/callback/google` | `infrastructure/auth/routes.py` | Google OAuth |
| `POST/GET/PATCH/DELETE /api/v1/api-keys/*` | `modules/api_keys/routes.py` | Authenticated key management |
| `GET /admin/*` | `interfaces/admin/initialize.py` | SQLAdmin UI |
| `GET /docs`, `/redoc`, `/openapi.json` | FastAPI built-ins | Disabled in production unless `ENABLE_DOCS_IN_PRODUCTION=true` |
| `GET /health` | App factory | Liveness check |

## What's Next

Start with the basics:

1. **[Endpoints](endpoints.md)** - Common patterns for new routes
2. **[Pagination](pagination.md)** - List endpoints with paged responses
3. **[Exception Handling](exceptions.md)** - The boilerplate's exception model
4. **[API Versioning](versioning.md)** - Versioning strategy

Then go deeper:

5. **[Database Schemas](../database/schemas.md)** - Pydantic shapes used in routes
6. **[CRUD Operations](../database/crud.md)** - The data layer below the service
