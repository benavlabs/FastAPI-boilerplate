# Database Layer

Learn how to work with the database layer in the FastAPI Boilerplate. This section covers everything you need to store and retrieve data effectively.

## What You'll Learn

- **[Models](models.md)** - Define database tables with SQLAlchemy 2.0
- **[Schemas](schemas.md)** - Validate and serialize data with Pydantic
- **[CRUD Operations](crud.md)** - Database access via FastCRUD
- **[Migrations](migrations.md)** - Manage schema changes with Alembic
- **[Neon](neon.md)** - Run on serverless Postgres instead of a local container

## Quick Overview

The boilerplate splits the data layer across each feature module so a feature owns its full stack:

```python
# modules/user/routes.py — request comes in, validated by UserCreate
@router.post("/", response_model=UserRead)
async def create_user(
    user: UserCreate,
    db: Annotated[AsyncSession, Depends(async_session)],
    user_service: Annotated[UserService, Depends(get_user_service)],
):
    return await user_service.create(user, db)

# modules/user/service.py — business logic, calls into FastCRUD
# modules/user/crud.py    — crud_users = FastCRUD(User)
# modules/user/models.py  — User SQLAlchemy model
```

## Architecture

```text
HTTP Request
    ↓
Pydantic Schema      (modules/<feature>/schemas.py)
    ↓
APIRouter            (modules/<feature>/routes.py)
    ↓
Service              (modules/<feature>/service.py)
    ↓
FastCRUD             (modules/<feature>/crud.py)
    ↓
SQLAlchemy Model     (modules/<feature>/models.py)
    ↓
PostgreSQL
```

The service layer holds business rules (permission checks, multi-step orchestration). FastCRUD handles the boilerplate query plumbing. The model defines the table.

## Key Components

### SQLAlchemy 2.0 Models

Models inherit from `Base` (a `DeclarativeBase` + `MappedAsDataclass` combination) and the relevant mixins:

```python
# modules/user/models.py
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from ...infrastructure.database.session import Base
from ...infrastructure.database.models import SoftDeleteMixin, TimestampMixin


class User(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "user"

    id: Mapped[int] = mapped_column(primary_key=True, init=False)
    username: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(100))
```

Available mixins from `infrastructure/database/models.py`:

- `TimestampMixin` — adds `created_at` and `updated_at`
- `SoftDeleteMixin` — adds `is_deleted` and `deleted_at`
- `UUIDMixin` — UUID primary key (alternative to integer ids)

### Pydantic Schemas

Schemas live alongside the model and split into request/response shapes:

```python
# modules/user/schemas.py
from pydantic import BaseModel, EmailStr, Field


class UserCreate(BaseModel):
    name: str = Field(min_length=2, max_length=30)
    username: str = Field(min_length=2, max_length=20)
    email: EmailStr
    password: str = Field(min_length=8)


class UserRead(BaseModel):
    id: int
    name: str
    username: str
    email: EmailStr
    # No hashed_password — schemas exclude sensitive fields
```

### FastCRUD Operations

Each module exposes a thin FastCRUD wrapper:

```python
# modules/user/crud.py
from fastcrud import FastCRUD
from .models import User

crud_users: FastCRUD = FastCRUD(User)
```

Then in the service:

```python
# modules/user/service.py
from .crud import crud_users

# Create
user = await crud_users.create(db=db, object=user_create)

# Read one
user = await crud_users.get(db=db, id=user_id)

# Read many
result = await crud_users.get_multi(db=db, offset=0, limit=10)

# Update
await crud_users.update(db=db, object=user_update, id=user_id)

# Soft delete (sets is_deleted=True via the mixin)
await crud_users.delete(db=db, id=user_id)

# Hard delete
await crud_users.db_delete(db=db, id=user_id)
```

### Database Migrations

Run from `backend/`:

```bash
# Generate a migration from model changes
uv run alembic revision --autogenerate -m "Add user table"

# Apply migrations
uv run alembic upgrade head

# Roll back the most recent migration
uv run alembic downgrade -1
```

## Database Setup

The boilerplate uses async PostgreSQL via `asyncpg`.

### Environment Configuration

```env
# backend/.env
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
POSTGRES_SERVER=localhost     # or "db" for Docker Compose
POSTGRES_PORT=5432
POSTGRES_DB=postgres
POSTGRES_ASYNC_PREFIX=postgresql+asyncpg://
POSTGRES_POOL_SIZE=20
POSTGRES_MAX_OVERFLOW=0
CREATE_TABLES_ON_STARTUP=true
```

The `DATABASE_URL` property on `DatabaseSettings` is computed from these. If you set `DATABASE_URL` directly in the environment it overrides everything else.

### Connection Management

The session dependency lives in `infrastructure/database/session.py`:

```python
from collections.abc import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession


async def async_session() -> AsyncGenerator[AsyncSession, None]:
    async with local_session() as db:
        yield db
```

Use it in routes via FastAPI's `Depends`:

```python
from typing import Annotated
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.database.session import async_session


@router.get("/")
async def list_users(
    db: Annotated[AsyncSession, Depends(async_session)],
):
    ...
```

## Included Models

The boilerplate ships with these models (one per feature module):

### `User` — `modules/user/models.py`
- Username, email, hashed password, full name, profile image
- OAuth fields: `oauth_provider`, `google_id`, `github_id`
- Foreign key to `tier`
- Mixins: `TimestampMixin`, `SoftDeleteMixin`
- Table name: **`user`** (singular)

### `Tier` — `modules/tier/models.py`
- Just `name` and `description` — no pricing or business logic
- One-to-many relationship with users
- Mixins: `TimestampMixin`, `SoftDeleteMixin`
- Table name: **`tiers`**

### `RateLimit` — `modules/rate_limit/models.py`
- Per-tier rate limits keyed by API path
- Fields: `tier_id`, `name`, `path`, `limit`, `period`
- Mixins: `TimestampMixin`, `SoftDeleteMixin`
- Table name: **`rate_limits`**

### `APIKey`, `KeyUsage`, `KeyPermission` — `modules/api_keys/models.py`
- API key issuance with per-key permissions and usage tracking
- Table names: `api_keys`, `key_usage`, `key_permissions`

## Directory Structure

Each feature owns its data stack:

```text
backend/src/
├── infrastructure/
│   └── database/
│       ├── session.py        # engine, async_session dep, Base class, create_tables
│       └── models.py         # TimestampMixin, SoftDeleteMixin, UUIDMixin
└── modules/
    ├── user/
    │   ├── models.py         # SQLAlchemy User
    │   ├── schemas.py        # Pydantic UserCreate/UserRead/UserUpdate
    │   ├── crud.py           # crud_users = FastCRUD(User)
    │   ├── service.py        # UserService (business rules)
    │   └── routes.py         # /api/v1/users endpoints
    ├── tier/
    ├── rate_limit/
    └── api_keys/
```

The shared `Base` and mixins are in `infrastructure/database/`. Everything feature-specific is colocated under the module.

## Common Patterns

### Create with Validation

```python
@router.post("/", response_model=UserRead, status_code=201)
async def create_user(
    user: UserCreate,
    db: Annotated[AsyncSession, Depends(async_session)],
    user_service: Annotated[UserService, Depends(get_user_service)],
):
    # service.create checks for duplicate username/email and hashes the password
    return await user_service.create(user, db)
```

### Query with Filters

```python
# Active users only (excludes soft-deleted)
result = await crud_users.get_multi(
    db=db,
    is_deleted=False,
    offset=0,
    limit=10,
)

# Substring search
result = await crud_users.get_multi(
    db=db,
    username__icontains="john",
    schema_to_select=UserRead,
)
```

FastCRUD supports `__` operators on field names (`__contains`, `__icontains`, `__gt`, `__lt`, `__in`, etc.).

### Soft Delete Pattern

The `SoftDeleteMixin` adds `is_deleted` and `deleted_at`. FastCRUD's `.delete()` flips the flag without removing the row:

```python
# Soft delete (default for models with the mixin)
await crud_users.delete(db=db, id=user_id)

# Hard delete (actually DELETE FROM)
await crud_users.db_delete(db=db, id=user_id)

# Filter to exclude soft-deleted records
await crud_users.get_multi(db=db, is_deleted=False)
```

## What's Next

1. **[Models](models.md)** - Define your tables and relationships
2. **[Schemas](schemas.md)** - Add Pydantic validation and serialization
3. **[CRUD Operations](crud.md)** - Use FastCRUD to read and write data
4. **[Migrations](migrations.md)** - Track and deploy schema changes
