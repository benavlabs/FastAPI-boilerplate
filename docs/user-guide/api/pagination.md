# API Pagination

The boilerplate uses FastCRUD's `PaginatedListResponse[T]` and `paginated_response()` helpers for paginated list endpoints. This page documents the pattern.

## Quick Start

```python
from typing import Any

from fastapi import APIRouter
from fastcrud import PaginatedListResponse, compute_offset, paginated_response

from ...infrastructure.dependencies import AsyncSessionDep
from .dependencies import UserServiceDep
from .schemas import UserRead


@router.get("/", response_model=PaginatedListResponse[UserRead])
async def get_users(
    db: AsyncSessionDep,
    user_service: UserServiceDep,
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

`compute_offset(page, items_per_page)` is the documented helper — use it instead of computing `(page - 1) * items_per_page` by hand.

## Response Shape

`paginated_response()` returns:

```json
{
  "data": [
    { "id": 1, "name": "User Userson", "username": "userson", "email": "user@example.com" }
  ],
  "total_count": 150,
  "has_more": true,
  "page": 1,
  "items_per_page": 10
}
```

`has_more` is `True` when there are still rows past the current page (`page * items_per_page < total_count`). The boilerplate doesn't return `total_pages` — frontends can derive it as `ceil(total_count / items_per_page)` if they need it.

## Where the Service Does the Work

The route stays thin. The actual `get_multi` call lives in the service:

```python
# modules/user/service.py
from fastcrud.types import GetMultiResponseDict
from .crud import crud_users
from .schemas import UserRead


class UserService:
    async def get_paginated(
        self, db: AsyncSession, skip: int = 0, limit: int = 100,
    ) -> GetMultiResponseDict:
        return await crud_users.get_multi(
            db=db,
            offset=skip,
            limit=limit,
            is_deleted=False,
            schema_to_select=UserRead,
            return_total_count=True,
        )
```

`return_total_count=True` is what makes the response include `total_count` (and therefore makes `has_more` accurate).

## Filtering

Add filter parameters to the route, pass them to the service:

```python
@router.get("/", response_model=PaginatedListResponse[UserRead])
async def list_users(
    db: Annotated[AsyncSession, Depends(async_session)],
    user_service: Annotated[UserService, Depends(get_user_service)],
    page: int = 1,
    items_per_page: int = 10,
    search: str | None = None,
    tier_id: int | None = None,
) -> dict[str, Any]:
    result = await user_service.get_paginated(
        skip=compute_offset(page, items_per_page),
        limit=items_per_page,
        db=db,
        search=search,
        tier_id=tier_id,
    )
    return paginated_response(crud_data=result, page=page, items_per_page=items_per_page)
```

In the service, build the `crud_users.get_multi` filters:

```python
async def get_paginated(
    self,
    db: AsyncSession,
    skip: int = 0,
    limit: int = 100,
    search: str | None = None,
    tier_id: int | None = None,
) -> GetMultiResponseDict:
    filters: dict[str, Any] = {"is_deleted": False}
    if tier_id is not None:
        filters["tier_id"] = tier_id
    if search:
        filters["username__icontains"] = search

    return await crud_users.get_multi(
        db=db,
        offset=skip,
        limit=limit,
        schema_to_select=UserRead,
        return_total_count=True,
        **filters,
    )
```

FastCRUD's `__icontains` / `__contains` / `__gt` / `__in` operators avoid raw SQL. See [CRUD Operations](../database/crud.md) for the full list.

## Sorting

FastCRUD accepts `sort_columns` and `sort_orders`:

```python
result = await crud_users.get_multi(
    db=db,
    offset=skip,
    limit=limit,
    sort_columns="created_at",
    sort_orders="desc",
    return_total_count=True,
)
```

For multiple sort keys, pass lists:

```python
sort_columns=["tier_id", "created_at"],
sort_orders=["asc", "desc"],
```

Expose this from the route as a query parameter:

```python
from fastapi import Query


@router.get("/", response_model=PaginatedListResponse[UserRead])
async def list_users(
    db: Annotated[AsyncSession, Depends(async_session)],
    user_service: Annotated[UserService, Depends(get_user_service)],
    page: int = 1,
    items_per_page: int = 10,
    sort_by: Annotated[str, Query(pattern=r"^(created_at|username|email)$")] = "created_at",
    sort_order: Annotated[str, Query(pattern=r"^(asc|desc)$")] = "desc",
) -> dict[str, Any]:
    ...
```

The `pattern` constraint stops clients from passing arbitrary column names that could leak fields you didn't mean to sort by.

## Validation

Always cap `items_per_page` to keep callers from asking for thousands of rows:

```python
from fastapi import Query


@router.get("/", response_model=PaginatedListResponse[UserRead])
async def list_users(
    db: Annotated[AsyncSession, Depends(async_session)],
    user_service: Annotated[UserService, Depends(get_user_service)],
    page: Annotated[int, Query(ge=1)] = 1,
    items_per_page: Annotated[int, Query(ge=1, le=100)] = 10,
) -> dict[str, Any]:
    ...
```

The boilerplate uses `ge=1, le=100` for the user list endpoint and `ge=1, le=1000` for API-key usage history (`modules/api_keys/routes.py`). Pick a cap that matches the row size of the model you're paginating.

## Real Endpoint: List Users

From `modules/user/routes.py`:

```python
@router.get(
    "/",
    response_model=PaginatedListResponse[UserRead],
    summary="List All Users (Admin)",
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Not authorized - requires admin privileges"},
    },
)
async def get_users(
    db: Annotated[AsyncSession, Depends(async_session)],
    _: Annotated[dict[str, Any], Depends(get_current_superuser)],
    user_service: Annotated[UserService, Depends(get_user_service)],
    page: int = 1,
    items_per_page: int = 10,
) -> dict[str, Any]:
    """Get paginated list of all users (admin only)."""
    users_data = await user_service.get_paginated(
        skip=compute_offset(page, items_per_page),
        limit=items_per_page,
        db=db,
    )
    return paginated_response(crud_data=users_data, page=page, items_per_page=items_per_page)
```

## Real Endpoint: API Key Usage History

From `modules/api_keys/routes.py` — same pattern, different limit cap:

```python
@router.get(
    "/{key_id}/usage",
    response_model=PaginatedListResponse[KeyUsageRead],
)
async def get_key_usage(
    current_user: CurrentUserDep,
    api_key_service: APIKeyServiceDep,
    db: AsyncSessionDep,
    key_id: int = Path(..., description="API key ID"),
    page: int = Query(1, ge=1, description="Page number"),
    items_per_page: int = Query(100, ge=1, le=1000, description="Items per page"),
) -> dict[str, Any]:
    result = await api_key_service.get_key_usage(
        key_id=key_id,
        user_id=current_user["id"] if isinstance(current_user, dict) else current_user.id,
        limit=items_per_page,
        offset=compute_offset(page, items_per_page),
        db=db,
    )
    return paginated_response(crud_data=result, page=page, items_per_page=items_per_page)
```

## Simple List Without Pagination

If you genuinely don't need pagination (e.g. an admin endpoint that returns a tiny enumerable like all tiers), call `get_multi` once and return the `data` list directly:

```python
@router.get("/all", response_model=list[TierRead])
async def list_all_tiers(
    db: Annotated[AsyncSession, Depends(async_session)],
    tier_service: Annotated[TierService, Depends(get_tier_service)],
) -> list[dict[str, Any]]:
    result = await tier_service.get_all(db=db, skip=0, limit=1000)
    return result["data"]
```

Even here, set a generous-but-finite `limit` — never an unbounded query.

## Performance Tips

### Cap `items_per_page`

Already covered, but worth repeating: an `Annotated[int, Query(ge=1, le=100)]` is your safety net.

### Use `schema_to_select`

Only return the columns the response model needs. For a `UserRead` schema, this avoids fetching `hashed_password`:

```python
return await crud_users.get_multi(
    db=db,
    schema_to_select=UserRead,
    return_total_count=True,
    offset=skip,
    limit=limit,
)
```

### Index columns you sort or filter on

When you add new sort/filter parameters that target a column without an index, generate an Alembic migration that adds one:

```python
def upgrade() -> None:
    op.create_index("ix_user_created_at", "user", ["created_at"])
```

The User model already indexes `username`, `email`, `tier_id`, `google_id`, and `github_id` for this reason.

### Beware of large offsets

`OFFSET 100000` still has Postgres scan and discard 100,000 rows. For very large datasets, consider keyset pagination (filtering by `created_at < cursor`) instead of page-based pagination. FastCRUD's `__lt` / `__gt` operators support this directly.

## What's Next

- **[CRUD Operations](../database/crud.md)** — Filter/sort/offset/limit semantics
- **[Schemas](../database/schemas.md)** — How `*Read` schemas pair with `schema_to_select`
- **[Authentication](../authentication/index.md)** — Gating list endpoints behind login or admin
