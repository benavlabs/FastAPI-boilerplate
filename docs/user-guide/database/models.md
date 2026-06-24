# Database Models

This page covers how SQLAlchemy 2.0 models are organized in the boilerplate, the patterns used for relationships and timestamps, and how to add a new model.

## Where Models Live

Models live in **`backend/src/modules/<feature>/models.py`** — colocated with that feature's schemas, CRUD, service, and routes:

```text
backend/src/modules/
├── user/models.py          # User
├── tier/models.py          # Tier
├── rate_limit/models.py    # RateLimit
└── api_keys/models.py      # APIKey, KeyUsage, KeyPermission
```

The shared base class and reusable mixins live in `backend/src/infrastructure/database/`:

```text
backend/src/infrastructure/database/
├── session.py              # Base, async_session, create_tables
└── models.py               # TimestampMixin, SoftDeleteMixin, UUIDMixin
```

## The Base Class

All models inherit from `Base` defined in `infrastructure/database/session.py`:

```python
from sqlalchemy.orm import DeclarativeBase, MappedAsDataclass


class Base(DeclarativeBase, MappedAsDataclass):
    """SQLAlchemy 2.0 base — also a dataclass for ergonomic instantiation."""
    pass
```

Combining `DeclarativeBase` with `MappedAsDataclass` means each model behaves like a Python dataclass: you instantiate it with `User(name=..., username=..., ...)` and only the columns you mark `init=False` are excluded from the constructor.

## Reusable Mixins

The boilerplate ships three mixins in `infrastructure/database/models.py`. Compose them onto your model:

```python
from ...infrastructure.database.models import (
    TimestampMixin,    # adds created_at, updated_at
    SoftDeleteMixin,   # adds is_deleted, deleted_at
    UUIDMixin,         # adds a uuid primary key (alternative to id)
)

class MyModel(Base, TimestampMixin, SoftDeleteMixin):
    ...
```

| Mixin | Adds | Notes |
|-------|------|-------|
| `TimestampMixin` | `created_at`, `updated_at` (timezone-aware UTC) | Both `init=False`; defaults via `datetime.now(UTC)` |
| `SoftDeleteMixin` | `is_deleted` (bool), `deleted_at` (datetime?) | FastCRUD's `.delete()` flips these instead of issuing `DELETE FROM` |
| `UUIDMixin` | `uuid` primary key with `gen_random_uuid()` server fallback | Use this when you need an external-facing identifier |

## Auto-Discovery for Alembic

Each module's models are imported in `backend/src/modules/__init__.py`:

```python
from .api_keys.models import APIKey, KeyPermission, KeyUsage
from .rate_limit.models import RateLimit
from .tier.models import Tier
from .user.models import User
```

When you add a new module, **add its models here** so Alembic's `--autogenerate` sees them.

## Relationships

The boilerplate uses SQLAlchemy `relationship()` where it makes sense, with `lazy="selectin"` to avoid N+1 problems by fetching related rows in a single follow-up query.

For example, `User.tier` and `Tier.users` are both wired up:

```python
# modules/user/models.py
class User(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "user"
    ...
    tier_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("tiers.id"), index=True, default=None,
    )
    tier: Mapped["Tier | None"] = relationship(
        "Tier", back_populates="users", lazy="selectin", init=False,
    )

# modules/tier/models.py
class Tier(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "tiers"
    ...
    users: Mapped[list["User"]] = relationship(
        "User", back_populates="tier", lazy="selectin",
        default_factory=list, init=False,
    )
```

### Avoiding Circular Imports

Both sides of a relationship import each other's model class. Use `TYPE_CHECKING` for the import and a string-literal class name in `relationship(...)`:

```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..tier.models import Tier


class User(Base, ...):
    tier: Mapped["Tier | None"] = relationship("Tier", back_populates="users", ...)
```

### When to Skip Relationships

If a foreign key only points "outward" (no need to traverse from the other side), just keep the FK column and skip the relationship:

```python
class APIKey(Base, ...):
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), index=True)
    # No User relationship — the API key knows its user via user_id;
    # users don't need a list of all their keys at the ORM level.
```

You can always join via FastCRUD when you need the related data.

## The User Model

`modules/user/models.py` is the most feature-rich example. Trimmed view:

```python
from datetime import datetime
from typing import TYPE_CHECKING
from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ...infrastructure.database.models import SoftDeleteMixin, TimestampMixin
from ...infrastructure.database.session import Base

if TYPE_CHECKING:
    from ..tier.models import Tier


class User(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "user"

    id: Mapped[int] = mapped_column(
        "id", autoincrement=True, nullable=False, unique=True,
        primary_key=True, init=False,
    )

    # Profile
    name: Mapped[str] = mapped_column(String(30))
    username: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(100))
    profile_image_url: Mapped[str] = mapped_column(
        String, default="https://profileimageurl.com",
    )

    # Tier (foreign key + relationship)
    tier_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("tiers.id"), index=True, default=None,
    )
    tier: Mapped["Tier | None"] = relationship(
        "Tier", back_populates="users", lazy="selectin", init=False,
    )

    is_superuser: Mapped[bool] = mapped_column(default=False)

    # OAuth fields (filled when user signs in via Google/GitHub)
    google_id: Mapped[str | None] = mapped_column(String(50), unique=True, index=True, default=None)
    github_id: Mapped[str | None] = mapped_column(String(50), unique=True, index=True, default=None)
    oauth_provider: Mapped[str | None] = mapped_column(String(20), default=None)
    email_verified: Mapped[bool] = mapped_column(default=False)

    @property
    def is_active(self) -> bool:
        return not self.is_deleted
```

Key points:

- `init=False` excludes the field from the dataclass `__init__` (used for the primary key and timestamps you don't want callers to set).
- `index=True` adds a database index on lookup-heavy columns (`username`, `email`, `tier_id`, OAuth IDs).
- `unique=True` enforces uniqueness at the DB level.
- `is_active` is a **derived property**, not a column — it returns `not is_deleted`. The `crudauth` auth library reads it during login so soft-deleted users can't authenticate, while `is_deleted` stays the single source of truth.

## The RateLimit Model

`modules/rate_limit/models.py` shows a no-relationship model with a foreign key:

```python
from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from ...infrastructure.database import Base
from ...infrastructure.database.models import SoftDeleteMixin, TimestampMixin


class RateLimit(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "rate_limits"

    id: Mapped[int] = mapped_column(
        "id", autoincrement=True, nullable=False, unique=True,
        primary_key=True, init=False,
    )
    tier_id: Mapped[int] = mapped_column(ForeignKey("tiers.id"), index=True)
    name: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    path: Mapped[str] = mapped_column(String, nullable=False)
    limit: Mapped[int] = mapped_column(Integer, nullable=False)
    period: Mapped[int] = mapped_column(Integer, nullable=False)
```

Each rate limit row says: "for tier X, requests to `path` are capped at `limit` per `period` seconds."

## Soft Deletion

The `SoftDeleteMixin` adds `is_deleted` and `deleted_at`. FastCRUD's `.delete()` flips them instead of removing the row:

```python
# Soft delete (default for models with the mixin)
await crud_users.delete(db=db, id=user_id)

# Actual DELETE FROM
await crud_users.db_delete(db=db, id=user_id)

# Filter out soft-deleted rows
await crud_users.get_multi(db=db, is_deleted=False)
```

## Adding a New Model

### Step-by-step

1. **Create the module folder** (if it doesn't exist): `mkdir -p backend/src/modules/widgets`
2. **Define the model** in `modules/widgets/models.py`
3. **Register it** in `modules/__init__.py` so Alembic sees it
4. **Generate a migration**: `cd backend && uv run alembic revision --autogenerate -m "add widgets"`
5. **Review the migration** in `migrations/versions/...` (autogenerate isn't always perfect)
6. **Apply**: `uv run alembic upgrade head`

### Example: a `Widget` model

```python
# backend/src/modules/widgets/models.py
from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ...infrastructure.database.models import SoftDeleteMixin, TimestampMixin
from ...infrastructure.database.session import Base


class Widget(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "widgets"

    id: Mapped[int] = mapped_column(
        "id", autoincrement=True, nullable=False, unique=True,
        primary_key=True, init=False,
    )
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    owner_id: Mapped[int] = mapped_column(ForeignKey("user.id"), index=True)
```

Then add to `backend/src/modules/__init__.py`:

```python
from .widgets.models import Widget

__all__ = [
    # ...existing exports...
    "Widget",
]
```

## Common Patterns

### Database-Level Constraints

```python
from sqlalchemy import CheckConstraint, Index, UniqueConstraint


class Product(Base, TimestampMixin):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True, init=False)
    price_cents: Mapped[int] = mapped_column(nullable=False)
    quantity: Mapped[int] = mapped_column(nullable=False)
    sku: Mapped[str] = mapped_column(String(50))
    org_id: Mapped[int] = mapped_column(ForeignKey("orgs.id"))

    __table_args__ = (
        CheckConstraint("price_cents > 0", name="positive_price"),
        CheckConstraint("quantity >= 0", name="non_negative_quantity"),
        UniqueConstraint("org_id", "sku", name="uq_org_sku"),
        Index("ix_product_price", "price_cents"),
    )
```

### Enum Fields

The boilerplate prefers `StrEnum` (used in `OAuthProvider`, `EnvironmentOption`, etc.):

```python
from enum import StrEnum
from sqlalchemy import String


class WidgetStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    ARCHIVED = "archived"


class Widget(Base, TimestampMixin):
    __tablename__ = "widgets"

    id: Mapped[int] = mapped_column(primary_key=True, init=False)
    status: Mapped[str] = mapped_column(String(20), default=WidgetStatus.ACTIVE.value)
```

Storing the value as a `String` keeps migrations simple. If you prefer SQLAlchemy's `SQLEnum` with a real Postgres enum type, that's also fine — just be aware that adding values requires a migration.

### JSON Fields

```python
from sqlalchemy.dialects.postgresql import JSONB


class UserProfile(Base, TimestampMixin):
    __tablename__ = "user_profiles"

    id: Mapped[int] = mapped_column(primary_key=True, init=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), unique=True)
    preferences: Mapped[dict] = mapped_column(JSONB, default_factory=dict, init=False)
```

## Migration Considerations

### Backwards-compatible changes (safe)

- Adding nullable columns
- Adding new tables
- Adding indexes
- Increasing string column lengths

### Breaking changes (need care)

- Making columns non-nullable (need a default or backfill plan)
- Removing columns (drop after deploy is stable)
- Changing column types (often two-step: add new, migrate data, drop old)
- Removing tables

See [Migrations](migrations.md) for the full workflow.

## Next Steps

1. **[Schemas](schemas.md)** - Pydantic request/response shapes
2. **[CRUD Operations](crud.md)** - FastCRUD usage patterns
3. **[Migrations](migrations.md)** - Alembic workflow
