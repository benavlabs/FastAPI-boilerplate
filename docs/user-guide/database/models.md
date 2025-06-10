# Database Models

This section explains how SQLAlchemy models are implemented in the boilerplate, how to create new models, and the patterns used for relationships, validation, and data integrity.

## Model Structure

Models are defined in `src/app/models/` using SQLAlchemy 2.0's declarative syntax with `Mapped` type annotations.

### Base Model

All models inherit from `Base` defined in `src/app/core/db/database.py`:

```python
from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    pass
```

**SQLAlchemy 2.0 Change**: Uses `DeclarativeBase` instead of the older `declarative_base()` function. This provides better type checking and IDE support.

### Model File Structure

Each model is in its own file:

```text
src/app/models/
├── __init__.py          # Imports all models for Alembic discovery
├── user.py             # User authentication model
├── post.py             # Example content model with relationships
├── tier.py             # User subscription tiers
└── rate_limit.py       # API rate limiting configuration
```

**Import Requirement**: Models must be imported in `__init__.py` for Alembic to detect them during migration generation.

## Design Decision: No SQLAlchemy Relationships

The boilerplate deliberately avoids using SQLAlchemy's `relationship()` feature. This is an intentional architectural choice with specific benefits.

### Why No Relationships

**Performance Concerns**:

- **N+1 Query Problem**: Relationships can trigger multiple queries when accessing related data
- **Lazy Loading**: Unpredictable when queries execute, making performance optimization difficult
- **Memory Usage**: Loading large object graphs consumes significant memory

**Code Clarity**:

- **Explicit Data Fetching**: Developers see exactly what data is being loaded and when
- **Predictable Queries**: No "magic" queries triggered by attribute access
- **Easier Debugging**: SQL queries are explicit in the code, not hidden in relationship configuration

**Flexibility**:

- **Query Optimization**: Can optimize each query for its specific use case
- **Selective Loading**: Load only the fields needed for each operation
- **Join Control**: Use FastCRUD's join methods when needed, skip when not

### What This Means in Practice

Instead of this (traditional SQLAlchemy):
```python
# Not used in the boilerplate
class User(Base):
    posts: Mapped[List["Post"]] = relationship("Post", back_populates="created_by_user")

class Post(Base):
    created_by_user: Mapped["User"] = relationship("User", back_populates="posts")
```

The boilerplate uses this approach:
```python
# DO - Explicit and controlled
class User(Base):
    # Only foreign key, no relationship
    tier_id: Mapped[int | None] = mapped_column(ForeignKey("tier.id"), index=True, default=None)

class Post(Base):
    # Only foreign key, no relationship  
    created_by_user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), index=True)

# Explicit queries - you control exactly what's loaded
user = await crud_users.get(db=db, id=1)
posts = await crud_posts.get_multi(db=db, created_by_user_id=user.id)

# Or use joins when needed
posts_with_users = await crud_posts.get_multi_joined(
    db=db,
    join_model=User,
    schema_to_select=PostRead,
    join_schema_to_select=UserRead
)
```

### Benefits of This Approach

**Predictable Performance**:

- Every database query is explicit in the code
- No surprise queries from accessing relationships
- Easier to identify and optimize slow operations

**Better Caching**:

- Can cache individual models without worrying about related data
- Cache invalidation is simpler and more predictable

**API Design**:

- Forces thinking about what data clients actually need
- Prevents over-fetching in API responses
- Encourages lean, focused endpoints

**Testing**:

- Easier to mock database operations
- No complex relationship setup in test fixtures
- More predictable test data requirements

### When You Need Related Data

Use FastCRUD's join capabilities:

```python
# Single record with related data
post_with_author = await crud_posts.get_joined(
    db=db,
    join_model=User,
    schema_to_select=PostRead,
    join_schema_to_select=UserRead,
    id=post_id
)

# Multiple records with joins
posts_with_authors = await crud_posts.get_multi_joined(
    db=db,
    join_model=User,
    offset=0,
    limit=10
)
```

### Alternative Approaches

If you need relationships in your project, you can add them:

```python
# Add relationships if needed for your use case
from sqlalchemy.orm import relationship

class User(Base):
    # ... existing fields ...
    posts: Mapped[List["Post"]] = relationship("Post", back_populates="created_by_user")

class Post(Base):
    # ... existing fields ...
    created_by_user: Mapped["User"] = relationship("User", back_populates="posts")
```

But consider the trade-offs and whether explicit queries might be better for your use case.

## User Model Implementation

The User model (`src/app/models/user.py`) demonstrates authentication patterns:

```python
import uuid as uuid_pkg
from datetime import UTC, datetime
from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column
from ..core.db.database import Base

class User(Base):
    __tablename__ = "user"

    id: Mapped[int] = mapped_column("id", autoincrement=True, nullable=False, unique=True, primary_key=True, init=False)
    
    # User data
    name: Mapped[str] = mapped_column(String(30))
    username: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String)
    
    # Profile
    profile_image_url: Mapped[str] = mapped_column(String, default="https://profileimageurl.com")
    
    # UUID for external references
    uuid: Mapped[uuid_pkg.UUID] = mapped_column(default_factory=uuid_pkg.uuid4, primary_key=True, unique=True)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default_factory=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    
    # Status flags
    is_deleted: Mapped[bool] = mapped_column(default=False, index=True)
    is_superuser: Mapped[bool] = mapped_column(default=False)
    
    # Foreign key to tier system (no relationship defined)
    tier_id: Mapped[int | None] = mapped_column(ForeignKey("tier.id"), index=True, default=None, init=False)
```

### Key Implementation Details

**Type Annotations**: `Mapped[type]` provides type hints for SQLAlchemy 2.0. IDE and mypy can validate types.

**String Lengths**: Explicit lengths (`String(50)`) prevent database errors and define constraints clearly.

**Nullable Fields**: Explicitly set `nullable=False` for required fields, `nullable=True` for optional ones.

**Default Values**: Use `default=` for database-level defaults, Python functions for computed defaults.

## Post Model with Relationships

The Post model (`src/app/models/post.py`) shows relationships and soft deletion:

```python
import uuid as uuid_pkg
from datetime import UTC, datetime
from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column
from ..core.db.database import Base

class Post(Base):
    __tablename__ = "post"

    id: Mapped[int] = mapped_column("id", autoincrement=True, nullable=False, unique=True, primary_key=True, init=False)
    
    # Content
    title: Mapped[str] = mapped_column(String(30))
    text: Mapped[str] = mapped_column(String(63206))  # Large text field
    media_url: Mapped[str | None] = mapped_column(String, default=None)
    
    # UUID for external references
    uuid: Mapped[uuid_pkg.UUID] = mapped_column(default_factory=uuid_pkg.uuid4, primary_key=True, unique=True)
    
    # Foreign key (no relationship defined)
    created_by_user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), index=True)
    
    # Timestamps (built-in soft delete pattern)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default_factory=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    is_deleted: Mapped[bool] = mapped_column(default=False, index=True)
```

### Soft Deletion Pattern

Soft deletion is built directly into models:

```python
# Built into each model that needs soft deletes
class Post(Base):
    # ... other fields ...
    
    # Soft delete fields
    is_deleted: Mapped[bool] = mapped_column(default=False, index=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
```

**Usage**: When `crud_posts.delete()` is called, it sets `is_deleted=True` and `deleted_at=datetime.now(UTC)` instead of removing the database row.

## Tier and Rate Limiting Models

### Tier Model

```python
# src/app/models/tier.py
class Tier(Base):
    __tablename__ = "tier"
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, init=False)
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
```

### Rate Limit Model

```python
# src/app/models/rate_limit.py
class RateLimit(Base):
    __tablename__ = "rate_limit"
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, init=False)
    tier_id: Mapped[int] = mapped_column(ForeignKey("tier.id"), nullable=False)
    path: Mapped[str] = mapped_column(String(255), nullable=False)
    limit: Mapped[int] = mapped_column(nullable=False)  # requests allowed
    period: Mapped[int] = mapped_column(nullable=False)  # time period in seconds
    name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
```

**Purpose**: Links API endpoints (`path`) to rate limits (`limit` requests per `period` seconds) for specific user tiers.

## Creating New Models

### Step-by-Step Process

1. **Create model file** in `src/app/models/your_model.py`
2. **Define model class** inheriting from `Base`
3. **Add to imports** in `src/app/models/__init__.py`
4. **Generate migration** with `alembic revision --autogenerate`
5. **Apply migration** with `alembic upgrade head`

### Example: Creating a Category Model

```python
# src/app/models/category.py
from datetime import datetime
from typing import List
from sqlalchemy import String, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.db.database import Base

class Category(Base):
    __tablename__ = "category"
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, init=False)
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
```

If you want to relate Category to Post, just add the id reference in the model:

```python
class Post(Base):
    __tablename__ = "post"
    ...
    
    # Foreign key (no relationship defined)
    category_id: Mapped[int] = mapped_column(ForeignKey("category.id"), index=True)
```

### Import in __init__.py

```python
# src/app/models/__init__.py
from .user import User
from .post import Post
from .tier import Tier
from .rate_limit import RateLimit
from .category import Category  # Add new model
```

**Critical**: Without this import, Alembic won't detect the model for migrations.

## Model Validation and Constraints

### Database-Level Constraints

```python
from sqlalchemy import CheckConstraint, Index

class Product(Base):
    __tablename__ = "product"
    
    price: Mapped[float] = mapped_column(nullable=False)
    quantity: Mapped[int] = mapped_column(nullable=False)
    
    # Table-level constraints
    __table_args__ = (
        CheckConstraint('price > 0', name='positive_price'),
        CheckConstraint('quantity >= 0', name='non_negative_quantity'),
        Index('idx_product_price', 'price'),
    )
```

### Unique Constraints

```python
# Single column unique
email: Mapped[str] = mapped_column(String(100), unique=True)

# Multi-column unique constraint
__table_args__ = (
    UniqueConstraint('user_id', 'category_id', name='unique_user_category'),
)
```

## Common Model Patterns

### Timestamp Tracking

```python
class TimestampedModel:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, 
        default=datetime.utcnow, 
        onupdate=datetime.utcnow, 
        nullable=False
    )

# Use as mixin
class Post(Base, TimestampedModel, SoftDeleteMixin):
    # Model automatically gets created_at, updated_at, is_deleted, deleted_at
    __tablename__ = "post"
    id: Mapped[int] = mapped_column(primary_key=True)
```

### Enumeration Fields

```python
from enum import Enum
from sqlalchemy import Enum as SQLEnum

class UserStatus(Enum):
    ACTIVE = "active"
    INACTIVE = "inactive" 
    SUSPENDED = "suspended"

class User(Base):
    status: Mapped[UserStatus] = mapped_column(SQLEnum(UserStatus), default=UserStatus.ACTIVE)
```

### JSON Fields

```python
from sqlalchemy.dialects.postgresql import JSONB

class UserProfile(Base):
    preferences: Mapped[dict] = mapped_column(JSONB, nullable=True)
    metadata: Mapped[dict] = mapped_column(JSONB, default=lambda: {})
```

**PostgreSQL-specific**: Uses JSONB for efficient JSON storage and querying.

## Model Testing

### Basic Model Tests

```python
# tests/test_models.py
import pytest
from sqlalchemy.exc import IntegrityError
from app.models.user import User

def test_user_creation():
    user = User(
        username="testuser",
        email="test@example.com", 
        hashed_password="hashed123"
    )
    assert user.username == "testuser"
    assert user.is_active is True  # Default value

def test_user_unique_constraint():
    # Test that duplicate emails raise IntegrityError
    with pytest.raises(IntegrityError):
        # Create users with same email
        pass
```

## Migration Considerations

### Backwards Compatible Changes

Safe changes that don't break existing code:

- Adding nullable columns
- Adding new tables
- Adding indexes
- Increasing column lengths

### Breaking Changes

Changes requiring careful migration:

- Making columns non-nullable
- Removing columns
- Changing column types
- Removing tables

## Next Steps

Now that you understand model implementation:

1. **[Schemas](schemas.md)** - Learn Pydantic validation and serialization
2. **[CRUD Operations](crud.md)** - Implement database operations with FastCRUD  
3. **[Migrations](migrations.md)** - Manage schema changes with Alembic

The next section covers how Pydantic schemas provide validation and API contracts separate from database models. 