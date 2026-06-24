# CRUD Operations

This guide covers the CRUD (Create, Read, Update, Delete) operations available in the boilerplate via [FastCRUD](https://benavlabs.github.io/fastcrud/).

## Overview

The boilerplate uses **FastCRUD** for all database access. It gives you:

- A consistent async API across every model
- Automatic pagination helpers
- Built-in soft delete support (when the model has `SoftDeleteMixin`)
- Selective field loading via `schema_to_select`
- Joined queries for related data

## Where CRUD Lives

Each module owns its own FastCRUD instance, kept tiny and predictable:

```python
# backend/src/modules/user/crud.py
from fastcrud import FastCRUD

from .models import User

crud_users: FastCRUD = FastCRUD(User)
```

```python
# backend/src/modules/tier/crud.py
from fastcrud import FastCRUD

from .models import Tier

crud_tiers: FastCRUD = FastCRUD(Tier)
```

The CRUD instance is then imported by the module's `service.py`, which adds business logic on top — input validation, permission checks, password hashing, multi-step orchestration.

```python
# Typical service method (modules/user/service.py)
from .crud import crud_users
from .schemas import UserCreate, UserCreateInternal, UserRead


async def create(self, user: UserCreate, db: AsyncSession) -> dict[str, Any]:
    if await crud_users.exists(db=db, email=user.email):
        raise UserExistsError("Email already registered")
    if await crud_users.exists(db=db, username=user.username):
        raise UserExistsError("Username already taken")

    payload = user.model_dump()
    payload["hashed_password"] = get_password_hash(payload.pop("password"))
    user_internal = UserCreateInternal(**payload)

    return await crud_users.create(db=db, object=user_internal, schema_to_select=UserRead)
```

## Read Operations

### Get a Single Record

```python
# By id
user = await crud_users.get(db=db, id=user_id)

# By any indexed field
user = await crud_users.get(db=db, username="userson")
user = await crud_users.get(db=db, email="user.userson@example.com")

# Restrict the returned shape with a Pydantic schema
user = await crud_users.get(
    db=db,
    schema_to_select=UserRead,
    username=username,
    is_deleted=False,
)
```

### Get Multiple Records

```python
# All non-deleted users, first 10
result = await crud_users.get_multi(
    db=db,
    is_deleted=False,
    offset=0,
    limit=10,
)
```

`get_multi` returns a dict shaped like:

```python
{
    "data": [...],
    "total_count": 25,
}
```

For full paginated responses (`page` / `has_more` / `items_per_page`), wrap the result with `paginated_response()` — see [Pagination](#pagination).

### Filter Operators

FastCRUD supports `__` operators on field names:

```python
# Substring match
await crud_users.get_multi(db=db, username__icontains="john")

# Range
await crud_users.get_multi(db=db, created_at__gt=cutoff_datetime)

# Set membership
await crud_users.get_multi(db=db, tier_id__in=[1, 2, 3])
```

Available operators include `__contains`, `__icontains`, `__startswith`, `__endswith`, `__gt`, `__ge`, `__lt`, `__le`, `__in`, `__not_in`, and others. See the [FastCRUD docs](https://benavlabs.github.io/fastcrud/) for the full list.

### Check Existence

```python
if await crud_users.exists(db=db, email="user@example.com"):
    raise UserExistsError("Email already registered")
```

`exists()` is faster than `get()` when you only need a yes/no — it doesn't transfer the row.

### Count Records

```python
total = await crud_users.count(db=db)
admins = await crud_users.count(db=db, is_superuser=True)
active = await crud_users.count(db=db, is_deleted=False)
```

## Create Operations

```python
user_internal = UserCreateInternal(
    name="User Userson",
    username="userson",
    email="user.userson@example.com",
    hashed_password=get_password_hash("Str1ngst!"),
)

created = await crud_users.create(db=db, object=user_internal)
```

The pattern in service code:

1. Validate the *external* schema (`UserCreate`) on input
2. Apply business rules (uniqueness check, password hashing, etc.)
3. Build the *internal* schema (`UserCreateInternal`) with the values you actually want to persist
4. Call `crud.create(db=db, object=internal_schema)`

Pass `schema_to_select=UserRead` if you want the returned dict trimmed to the public shape:

```python
created = await crud_users.create(db=db, object=user_internal, schema_to_select=UserRead)
```

### Creating Records with Foreign Keys

For models that reference other rows, just include the FK column on the create schema:

```python
new_rate_limit = RateLimitCreate(
    tier_id=tier.id,
    name="users_list",
    path="/api/v1/users/",
    limit=100,
    period=60,
)
await crud_rate_limits.create(db=db, object=new_rate_limit)
```

## Update Operations

```python
# Update by id
await crud_users.update(
    db=db,
    object=UserUpdate(email="newemail@example.com"),
    id=user_id,
)

# Update by any field
await crud_users.update(db=db, object=UserUpdate(name="New Name"), username=username)
```

Only fields set on the update schema are written — `*Update` schemas have every field as `Optional[T] = None`, and unset fields are skipped.

### Common Pattern: Validate Before Update

```python
# Service method
if values.username and values.username != db_user["username"]:
    if await crud_users.exists(db=db, username=values.username):
        raise UserExistsError("Username not available")

await crud_users.update(db=db, object=values, id=db_user["id"])
```

### Bulk Update

`update()` accepts the same lookup args as `get_multi()` — pass non-id criteria to update many rows:

```python
# Reset profile_image_url for everyone in a deprecated tier
await crud_users.update(
    db=db,
    object=UserUpdate(profile_image_url="https://www.profileimageurl.com"),
    tier_id=deprecated_tier_id,
)
```

## Delete Operations

### Soft Delete (default for models with `SoftDeleteMixin`)

```python
# Sets is_deleted=True and deleted_at=now()
await crud_users.delete(db=db, id=user_id)

# The row stays — query it explicitly
soft_deleted = await crud_users.get(db=db, id=user_id, is_deleted=True)
```

### Hard Delete

```python
# DELETE FROM user WHERE id = ?
await crud_users.db_delete(db=db, id=user_id)
```

### Filtering Out Soft-Deleted Records

Add `is_deleted=False` to your queries:

```python
active_users = await crud_users.get_multi(db=db, is_deleted=False, limit=10)
```

## Joined Queries

For models with relationships (e.g. `User.tier`), the relationship loads automatically via `lazy="selectin"`.

For ad-hoc joins without a configured relationship, use `get_joined` / `get_multi_joined`:

```python
posts_with_authors = await crud_posts.get_multi_joined(
    db=db,
    join_model=User,
    join_on=Post.created_by_user_id == User.id,
    schema_to_select=PostRead,
    join_schema_to_select=UserRead,
    join_prefix="author_",
    offset=0,
    limit=10,
)
# Each row: {..., "author_username": ..., "author_email": ...}
```

The boilerplate also uses **`JoinConfig`** for more complex multi-join queries (see `UserService.get_rate_limits` for a real example with two joins).

## Pagination

The boilerplate uses FastCRUD's `paginated_response()` helper to turn a `get_multi` result into a public-shaped paginated response:

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

Response shape:

```json
{
  "data": [{ "id": 1, "name": "...", "username": "..." }],
  "total_count": 150,
  "has_more": true,
  "page": 1,
  "items_per_page": 10
}
```

## Selective Field Loading

`schema_to_select` lets the database return only the columns the caller cares about. The result is a plain dict matching the schema fields:

```python
# Returns just id, name, username, email, profile_image_url, ...
result = await crud_users.get_multi(
    db=db,
    schema_to_select=UserRead,
    is_deleted=False,
    limit=100,
)
```

Use this when you want to avoid fetching `hashed_password` or other heavy fields you won't use.

## Complete Workflow Example

```python
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.user.crud import crud_users
from src.modules.user.schemas import (
    UserCreateInternal,
    UserRead,
    UserUpdate,
)
from crudauth import get_password_hash


async def user_lifecycle(db: AsyncSession) -> None:
    # 1. CREATE
    new_user = await crud_users.create(
        db=db,
        object=UserCreateInternal(
            name="Demo User",
            username="demo_user",
            email="demo@example.com",
            hashed_password=get_password_hash("Str1ngst!"),
        ),
        schema_to_select=UserRead,
    )

    # 2. READ
    fetched = await crud_users.get(
        db=db,
        id=new_user["id"],
        schema_to_select=UserRead,
    )

    # 3. UPDATE
    await crud_users.update(
        db=db,
        object=UserUpdate(name="Demo Userson"),
        id=fetched["id"],
    )

    # 4. SOFT DELETE
    await crud_users.delete(db=db, id=fetched["id"])

    # 5. FETCH SOFT-DELETED
    soft_deleted = await crud_users.get(db=db, id=fetched["id"], is_deleted=True)
    assert soft_deleted["deleted_at"] is not None
```

## Error Handling

Domain errors live in `modules/common/exceptions.py` (`UserExistsError`, `UserNotFoundError`, `ResourceNotFoundError`, `PermissionDeniedError`, etc.). Routes catch them and translate to HTTP errors via `modules/common/utils/error_handler.handle_exception`.

```python
async def create(self, user: UserCreate, db: AsyncSession) -> dict[str, Any]:
    if await crud_users.exists(db=db, email=user.email):
        raise UserExistsError("Email already registered")
    # ... create user ...
```

The route then:

```python
try:
    return await user_service.create(user, db)
except Exception as e:
    http_exc = handle_exception(e)
    if http_exc:
        raise http_exc
    raise HTTPException(status_code=500, detail="An unexpected error occurred")
```

## Performance Tips

### Use `schema_to_select`

Avoid loading columns you won't read:

```python
# Good — only the public fields
user = await crud_users.get(db=db, id=user_id, schema_to_select=UserRead)

# Avoid — pulls the password hash too
user = await crud_users.get(db=db, id=user_id)
```

### Use `exists()` for existence checks

```python
# Good — boolean, no row transfer
if await crud_users.exists(db=db, email=email):
    raise UserExistsError("Email taken")

# Avoid — fetches the entire row to check None
user = await crud_users.get(db=db, email=email)
if user:
    raise UserExistsError("Email taken")
```

### Use `count()` for counts

```python
# Good
total = await crud_users.count(db=db, is_deleted=False)

# Avoid
result = await crud_users.get_multi(db=db, is_deleted=False, limit=10000)
total = result["total_count"]  # works, but transfers data
```

### Pre-fetch related data in services

If a route calls `crud_users.get` then `crud_tiers.get(tier_id)` separately, prefer using the existing `User.tier` relationship (auto-loaded with `selectin`) or a `get_joined` call, so the database only round-trips once.

## Next Steps

- **[Migrations](migrations.md)** — Manage schema changes with Alembic
- **[API Endpoints](../api/endpoints.md)** — Wire CRUD into FastAPI routes
- **[Caching](../caching/index.md)** — Cache CRUD results
