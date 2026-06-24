# API Endpoints

This guide shows the patterns the boilerplate uses for endpoints, so adding new ones stays consistent with the existing modules.

## Dependency Injection

This boilerplate supports two equivalent ways to inject FastAPI dependencies — you'll see both in the codebase, and either is correct.

### Traditional style (explicit `Depends()`)

```python
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.database.session import async_session


@router.get("/items")
async def list_items(
    db: AsyncSession = Depends(async_session),
) -> list[dict[str, Any]]:
    ...
```

### Modern style (Annotated type aliases)

```python
from ...infrastructure.dependencies import AsyncSessionDep


@router.get("/items")
async def list_items(
    db: AsyncSessionDep,
) -> list[dict[str, Any]]:
    ...
```

The boilerplate pre-defines aliases for every shared dependency in `infrastructure/dependencies.py`:

| Alias | Resolves to |
|---|---|
| `AsyncSessionDep` | `Annotated[AsyncSession, Depends(async_session)]` |
| `CurrentUserDep` | `Annotated[dict[str, Any], Depends(get_current_user)]` |
| `CurrentSuperUserDep` | `Annotated[dict[str, Any], Depends(get_current_superuser)]` |
| `OptionalUserDep` | `Annotated[dict[str, Any] \| None, Depends(get_optional_user)]` |
| `OAuth2FormDep` | `Annotated[OAuth2PasswordRequestForm, Depends()]` |

Per-module service aliases live in `modules/<name>/dependencies.py`:

| File | Alias |
|---|---|
| `modules/user/dependencies.py` | `UserServiceDep` |
| `modules/tier/dependencies.py` | `TierServiceDep` |
| `modules/rate_limit/dependencies.py` | `RateLimitServiceDep` |
| `modules/api_keys/dependencies.py` | `APIKeyServiceDep` |

Both styles produce the same runtime behavior. The alias form reduces repetition and makes route signatures easier to scan.

## Quick Start

A typical endpoint lives in `modules/<feature>/routes.py` and delegates work to a service:

```python
# backend/src/modules/widgets/routes.py
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.auth.http_exceptions import HTTPException
from ...infrastructure.auth.dependencies import get_current_user
from ...infrastructure.database.session import async_session
from ..common.utils.error_handler import handle_exception
from .schemas import WidgetCreate, WidgetRead
from .service import WidgetService

router = APIRouter(tags=["Widgets"])


def get_widget_service() -> WidgetService:
    """Per-module service factory used by Depends()."""
    return WidgetService()


@router.get("/{widget_id}", response_model=WidgetRead)
async def get_widget(
    widget_id: int,
    db: Annotated[AsyncSession, Depends(async_session)],
    widget_service: Annotated[WidgetService, Depends(get_widget_service)],
) -> dict[str, Any]:
    """Get a widget by id."""
    try:
        widget = await widget_service.get_by_id(widget_id, db)
        if widget is None:
            raise HTTPException(status_code=404, detail=f"Widget {widget_id} not found")
        return widget
    except Exception as e:
        http_exc = handle_exception(e)
        if http_exc:
            raise http_exc
        raise HTTPException(status_code=500, detail="An unexpected error occurred")
```

Register the router in `interfaces/api/v1/__init__.py`:

```python
from ....modules.widgets.routes import router as widgets_router

router.include_router(widgets_router, prefix="/widgets")
```

The endpoint is now live at `GET /api/v1/widgets/{widget_id}`.

## Common Patterns

The pattern across every module is the same:

1. **Routes** define HTTP shape and delegate to a service
2. **Service** holds business logic (permission checks, multi-step orchestration)
3. **CRUD** does the database I/O

Below are the canonical patterns. They mirror what's already in `modules/user/routes.py`, `modules/tier/routes.py`, etc.

### Get a Single Item

```python
@router.get("/{widget_id}", response_model=WidgetRead)
async def get_widget(
    widget_id: int,
    db: Annotated[AsyncSession, Depends(async_session)],
    widget_service: Annotated[WidgetService, Depends(get_widget_service)],
) -> dict[str, Any]:
    try:
        widget = await widget_service.get_by_id(widget_id, db)
        if widget is None:
            raise HTTPException(status_code=404, detail=f"Widget {widget_id} not found")
        return widget
    except Exception as e:
        http_exc = handle_exception(e)
        if http_exc:
            raise http_exc
        raise HTTPException(status_code=500, detail="An unexpected error occurred")
```

### Get Multiple Items (Paginated)

```python
from fastcrud import PaginatedListResponse, compute_offset, paginated_response


@router.get("/", response_model=PaginatedListResponse[WidgetRead])
async def list_widgets(
    db: Annotated[AsyncSession, Depends(async_session)],
    widget_service: Annotated[WidgetService, Depends(get_widget_service)],
    page: int = 1,
    items_per_page: int = 10,
) -> dict[str, Any]:
    result = await widget_service.get_paginated(
        skip=compute_offset(page, items_per_page),
        limit=items_per_page,
        db=db,
    )
    return paginated_response(crud_data=result, page=page, items_per_page=items_per_page)
```

See [Pagination](pagination.md) for the full pattern.

### Create

```python
@router.post("/", response_model=WidgetRead, status_code=201)
async def create_widget(
    widget: WidgetCreate,
    db: Annotated[AsyncSession, Depends(async_session)],
    widget_service: Annotated[WidgetService, Depends(get_widget_service)],
) -> dict[str, Any]:
    try:
        return await widget_service.create(widget, db)
    except Exception as e:
        http_exc = handle_exception(e)
        if http_exc:
            raise http_exc
        raise HTTPException(status_code=500, detail="An unexpected error occurred")
```

The service does the duplicate check / business validation:

```python
# modules/widgets/service.py
async def create(self, widget: WidgetCreate, db: AsyncSession) -> dict[str, Any]:
    if await crud_widgets.exists(db=db, name=widget.name):
        raise ResourceExistsError("Widget with this name already exists")
    return await crud_widgets.create(db=db, object=widget, schema_to_select=WidgetRead)
```

### Update

```python
@router.patch("/{widget_id}", response_model=WidgetRead)
async def update_widget(
    widget_id: int,
    values: WidgetUpdate,
    db: Annotated[AsyncSession, Depends(async_session)],
    widget_service: Annotated[WidgetService, Depends(get_widget_service)],
) -> dict[str, Any]:
    try:
        return await widget_service.update(widget_id, values, db)
    except Exception as e:
        http_exc = handle_exception(e)
        if http_exc:
            raise http_exc
        raise HTTPException(status_code=500, detail="An unexpected error occurred")
```

### Delete (Soft Delete)

```python
@router.delete("/{widget_id}", status_code=204)
async def delete_widget(
    widget_id: int,
    db: Annotated[AsyncSession, Depends(async_session)],
    widget_service: Annotated[WidgetService, Depends(get_widget_service)],
) -> None:
    try:
        await widget_service.delete(widget_id, db)
    except Exception as e:
        http_exc = handle_exception(e)
        if http_exc:
            raise http_exc
        raise HTTPException(status_code=500, detail="An unexpected error occurred")
```

`crud_widgets.delete()` flips `is_deleted=True` if the model uses `SoftDeleteMixin`. Use `db_delete()` when you actually want to remove the row.

## Authentication

All session-based auth dependencies live in `infrastructure/auth/dependencies`.

### Require Login

```python
from ...infrastructure.auth.dependencies import get_current_user


@router.get("/me", response_model=WidgetRead)
async def my_widget(
    current_user: Annotated[dict[str, Any], Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(async_session)],
    widget_service: Annotated[WidgetService, Depends(get_widget_service)],
) -> dict[str, Any]:
    return await widget_service.get_by_owner(current_user["id"], db)
```

### Optional Auth

```python
from ...infrastructure.auth.dependencies import get_optional_user


@router.get("/", response_model=list[WidgetRead])
async def list_widgets(
    user: Annotated[dict[str, Any] | None, Depends(get_optional_user)],
    ...
):
    # Show extra fields when logged in
    ...
```

### Superuser Only

```python
from ...infrastructure.auth.dependencies import get_current_superuser


@router.delete("/{widget_id}/permanent")
async def hard_delete_widget(
    widget_id: int,
    db: Annotated[AsyncSession, Depends(async_session)],
    widget_service: Annotated[WidgetService, Depends(get_widget_service)],
    _: Annotated[dict[str, Any], Depends(get_current_superuser)],
) -> dict[str, str]:
    await widget_service.permanent_delete(widget_id, db)
    return {"message": "Widget permanently deleted"}
```

The leading underscore on the dependency-only parameter is the convention used across the boilerplate.

### API Key Authentication

For machine-to-machine clients, see [Authentication](../authentication/index.md). API keys are managed via the `/api/v1/api-keys/*` endpoints in `modules/api_keys/routes.py`.

## Path & Query Parameters

### Path Parameters

```python
@router.get("/{widget_id}")
async def get_widget(widget_id: int, ...):
    ...
```

FastAPI validates `widget_id` is an int automatically. Invalid input returns `422`.

### Simple Query Parameters

```python
@router.get("/search")
async def search_widgets(
    db: Annotated[AsyncSession, Depends(async_session)],
    widget_service: Annotated[WidgetService, Depends(get_widget_service)],
    name: str | None = None,
    is_active: bool = True,
) -> list[dict[str, Any]]:
    return await widget_service.search(db=db, name=name, is_active=is_active)
```

### Query Validation

```python
from fastapi import Query


@router.get("/")
async def list_widgets(
    db: Annotated[AsyncSession, Depends(async_session)],
    page: Annotated[int, Query(ge=1)] = 1,
    items_per_page: Annotated[int, Query(ge=1, le=100)] = 10,
    search: Annotated[str | None, Query(max_length=50)] = None,
):
    ...
```

## Error Handling

The boilerplate uses two layers of exceptions:

### Domain exceptions (services)

Defined in `modules/common/exceptions.py`:

- `ResourceNotFoundError`
- `ResourceExistsError`
- `PermissionDeniedError`
- `UserNotFoundError`, `UserExistsError`
- `TierNotFoundError`
- `ValidationError`

Service methods raise these — they don't know about HTTP.

### HTTP exceptions (routes)

Re-exported from FastCRUD in `infrastructure/auth/http_exceptions.py`:

- `HTTPException` (the FastAPI base)
- `BadRequestException` — 400
- `UnauthorizedException` — 401
- `ForbiddenException` — 403
- `NotFoundException` — 404
- `UnprocessableEntityException` — 422
- `DuplicateValueException` — 409
- `RateLimitException` — 429
- `CSRFException` — 403 with `X-CSRF-Error` header (defined locally for CSRF flows)

### The `handle_exception` Bridge

Routes wrap their work in a `try/except` and let `handle_exception()` map domain errors to HTTP errors:

```python
from ..common.utils.error_handler import handle_exception


try:
    return await widget_service.update(widget_id, values, db)
except Exception as e:
    http_exc = handle_exception(e)
    if http_exc:
        raise http_exc
    raise HTTPException(status_code=500, detail="An unexpected error occurred")
```

`handle_exception` returns the matching HTTP exception (or `None` for unrecognized errors, which become a 500).

### Direct HTTP Exceptions

When you have an immediate HTTP-shaped failure with no service involvement, raise directly:

```python
from ...infrastructure.auth.http_exceptions import NotFoundException


@router.get("/{name}", response_model=TierRead)
async def get_tier_by_name(...):
    try:
        return await tier_service.get_by_name(name, db)
    except TierNotFoundError:
        raise NotFoundException("Tier not found")
```

This pattern is used in `modules/tier/routes.py`. See [Exceptions](exceptions.md) for the full picture.

## File Uploads

```python
from fastapi import File, UploadFile


@router.post("/{user_id}/avatar")
async def upload_avatar(
    user_id: int,
    current_user: Annotated[dict[str, Any], Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(async_session)],
    file: UploadFile = File(...),
) -> dict[str, str]:
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image")

    # ...persist the file via your storage backend, then update the user...
    return {"message": "Avatar uploaded successfully"}
```

The boilerplate doesn't ship a default storage backend; pick one (local disk, S3, GCS) and add it as a settings group when you need it.

## Adding a New Endpoint Module

The full flow for adding `widgets`:

### 1. Create the Module

```bash
mkdir -p backend/src/modules/widgets
touch backend/src/modules/widgets/__init__.py
```

### 2. Add the Stack

| File | Contents |
|------|----------|
| `models.py` | SQLAlchemy `Widget` model (see [Models](../database/models.md)) |
| `schemas.py` | `WidgetCreate`, `WidgetRead`, `WidgetUpdate` (see [Schemas](../database/schemas.md)) |
| `crud.py` | `crud_widgets: FastCRUD = FastCRUD(Widget)` |
| `service.py` | `WidgetService` with `create`, `get_by_id`, `update`, `delete` methods |
| `routes.py` | `APIRouter` with the endpoints |

### 3. Register the Model

In `backend/src/modules/__init__.py`:

```python
from .widgets.models import Widget

__all__ = [..., "Widget"]
```

### 4. Mount the Router

In `backend/src/interfaces/api/v1/__init__.py`:

```python
from ....modules.widgets.routes import router as widgets_router

router.include_router(widgets_router, prefix="/widgets")
```

### 5. Generate a Migration

```bash
cd backend
uv run alembic revision --autogenerate -m "Add widgets table"
uv run alembic upgrade head
```

### 6. Test

```bash
curl http://localhost:8000/api/v1/widgets/
```

Your routes are now visible in `/docs`.

## Best Practices

1. **Delegate to a service** — keep `routes.py` thin. Routes handle HTTP; services hold rules.
2. **Use the `handle_exception` pattern** — uniform error translation across the codebase.
3. **Prefer `schema_to_select=`** — only return the columns the response model needs.
4. **Use `*Update` schemas with all fields optional** — partial updates are the convention.
5. **Match status codes to actions**: 201 on create, 204 on delete-with-no-body, 200 default.
6. **Keep route signatures consistent** — `db` and `<feature>_service` injected via `Annotated[..., Depends(...)]`, dependency-only auth as `_`.
7. **Don't import models across modules** — except for foreign-key relationships (and even then via `TYPE_CHECKING`).

## What's Next

- **[Pagination](pagination.md)** — Paginate list endpoints with `PaginatedListResponse`
- **[Exceptions](exceptions.md)** — The full exception model
- **[API Versioning](versioning.md)** — How `/api/v1/` is wired and how to add `/api/v2/`
- **[CRUD Operations](../database/crud.md)** — The data layer below your service
