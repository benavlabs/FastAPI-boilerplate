# Database Schemas

Pydantic schemas handle three things in this codebase: **input validation**, **output serialization**, and **API contracts** that frontend and backend can rely on. Schemas are separate from the SQLAlchemy models — keeping the two layers split lets you control exactly what each endpoint accepts and returns.

## Where Schemas Live

Each module owns its schemas, colocated with the model and CRUD:

```text
backend/src/modules/
├── user/schemas.py            # UserCreate, UserRead, UserUpdate, UserAnonymize, ...
├── tier/schemas.py            # TierCreate, TierRead, TierUpdate
├── rate_limit/schemas.py      # RateLimitCreate, RateLimitRead, RateLimitUpdate
└── api_keys/schemas.py        # APIKeyCreate, APIKeyRead, APIKeyUpdate, KeyUsageRead
```

Cross-module shared schemas (timestamp/soft-delete mixins, common error shapes) live in `backend/src/modules/common/schemas.py`.

## Common Mixin Schemas

`modules/common/schemas.py` provides two reusable Pydantic mixins matching the SQLAlchemy mixins:

```python
# modules/common/schemas.py
class TimestampSchema(BaseModel):
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC).replace(tzinfo=None))
    updated_at: datetime | None = Field(default=None)
    # serializers cast both to ISO strings


class PersistentDeletion(BaseModel):
    deleted_at: datetime | None = Field(default=None)
    is_deleted: bool = False
```

Compose them onto your full-record schema where applicable.

## The User Schemas

`modules/user/schemas.py` is the most extensive example. The pattern is **one schema per role** — each operation gets its own shape:

```python
from datetime import datetime
from typing import Annotated
from pydantic import BaseModel, ConfigDict, EmailStr, Field

from ..common.schemas import PersistentDeletion, TimestampSchema


# Declared once, reused by every schema that carries a username: the rule has to
# match the column (String(32)) and whatever OAuth provisioning generates
USERNAME_MAX_LENGTH = 32
USERNAME_PATTERN = r"^[a-z0-9_]+$"


# Common fields shared by create/update/full-record
class UserBase(BaseModel):
    name: Annotated[str, Field(min_length=2, max_length=30, examples=["User Userson"])]
    username: Annotated[
        str,
        Field(min_length=2, max_length=USERNAME_MAX_LENGTH, pattern=USERNAME_PATTERN, examples=["userson"]),
    ]
    email: Annotated[EmailStr, Field(examples=["user.userson@example.com"])]


# Full record (used internally — never returned to clients)
class User(TimestampSchema, UserBase, PersistentDeletion):
    hashed_password: str
    is_superuser: bool = False
    profile_image_url: str = "https://www.profileimageurl.com"
    tier_id: int | None = None

    # OAuth
    google_id: str | None = None
    github_id: str | None = None
    oauth_provider: str | None = None
    email_verified: bool = False


# API response — explicitly excludes sensitive fields
class UserRead(BaseModel):
    id: int
    name: Annotated[str, Field(min_length=2, max_length=30)]
    username: Annotated[str, Field(min_length=2, max_length=USERNAME_MAX_LENGTH, pattern=USERNAME_PATTERN)]
    email: EmailStr
    profile_image_url: str
    is_deleted: bool = False
    tier_id: int | None
    is_superuser: bool = False
    email_verified: bool = False
    oauth_provider: str | None = None


# API request body for POST /users/
class UserCreate(UserBase):
    model_config = ConfigDict(extra="forbid")  # reject unknown fields

    password: Annotated[
        str,
        Field(
            min_length=8,
            description=(
                "Password must be at least 8 characters and include a number, "
                "uppercase letter, lowercase letter, and special character"
            ),
            examples=["Str1ngst!"],
            pattern=r"^.{8,}|[0-9]+|[A-Z]+|[a-z]+|[^a-zA-Z0-9]+$",
        ),
    ]
    # OAuth fields — populated when user signs up via Google/GitHub
    google_id: str | None = None
    github_id: str | None = None
    oauth_provider: str | None = None


# What the service writes to the DB (raw password replaced with hash)
class UserCreateInternal(UserBase):
    hashed_password: str
    google_id: str | None = None
    github_id: str | None = None
    oauth_provider: str | None = None
    email_verified: bool = False


# Partial update — every field optional
class UserUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Annotated[str | None, Field(min_length=2, max_length=30, default=None)]
    username: Annotated[
        str | None,
        Field(min_length=2, max_length=USERNAME_MAX_LENGTH, pattern=USERNAME_PATTERN, default=None),
    ]
    email: Annotated[EmailStr | None, Field(default=None)]
    profile_image_url: Annotated[
        str | None,
        Field(pattern=r"^(https?|ftp)://[^\s/$.?#].[^\s]*$", default=None),
    ]


class UserUpdateInternal(UserUpdate):
    updated_at: datetime  # service stamps this before persisting


class UserTierUpdate(BaseModel):
    tier_id: int


class UserDelete(BaseModel):
    model_config = ConfigDict(extra="forbid")
    is_deleted: bool
    deleted_at: datetime


# GDPR/LGPD anonymization payload
class UserAnonymize(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    username: str
    hashed_password: str | None = None
    # ...other PII-clearing fields...
```

### Naming Conventions

The schemas follow a consistent vocabulary across modules:

| Suffix | Use |
|--------|-----|
| `Base` | Common fields shared across create/update/full schemas |
| *(none — class name = `User`)* | Full-record schema (every column, mostly internal) |
| `Read` | API response — drops sensitive/internal fields |
| `Create` | API request body for POST |
| `CreateInternal` | What the service stores (raw password → hashed_password) |
| `Update` | Partial update body for PATCH (all fields optional) |
| `UpdateInternal` | What the service stores on update (e.g. with stamped `updated_at`) |
| `TierUpdate`, `Anonymize`, `Delete`, … | Operation-specific narrow schemas |

### Why Internal vs External

The split between `Create` and `CreateInternal` (and likewise for updates) keeps the API surface honest:

- `UserCreate` accepts `password: str` from the client.
- The service hashes the password and constructs a `UserCreateInternal` with `hashed_password` instead.
- `crud_users.create(db=db, object=user_internal)` is what actually hits the database.

The client can never set `hashed_password` directly, and the model never sees a plaintext password.

## Field Validation

### `Annotated` + `Field`

The codebase uses `Annotated[T, Field(...)]` for validation rules:

| `Field` parameter | Effect |
|-------------------|--------|
| `min_length` / `max_length` | String length bounds |
| `pattern` | Regex validation (e.g. `r"^[a-z0-9]+$"` for usernames) |
| `gt` / `ge` / `lt` / `le` | Numeric bounds |
| `default` | Default value |
| `examples` | OpenAPI example values shown in `/docs` |
| `description` | Doc string visible in OpenAPI |

### `EmailStr`

Pydantic's `EmailStr` validates the email format and normalizes the casing.

### `ConfigDict(extra="forbid")`

Set on `UserCreate`, `UserUpdate`, etc. — anything the client sends beyond the declared fields raises a 422. This matters most for create/update payloads where stray fields could otherwise sneak through.

### `from_attributes`

Use `ConfigDict(from_attributes=True)` when you need to build a Pydantic schema from a SQLAlchemy model instance directly. The boilerplate's services mostly work with dicts (FastCRUD's default return shape), so this is rarely needed — but it's the right setting if you do `UserRead.model_validate(orm_user)`.

## Schema Patterns

### Optional Fields in Updates

The convention is **all fields optional** in `*Update` schemas:

```python
class UserUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Annotated[str | None, Field(min_length=2, max_length=30, default=None)]
    email: Annotated[EmailStr | None, Field(default=None)]
    # ...
```

The service then writes only the fields the client actually provided.

### Custom Validators

For cross-field rules or transforms:

```python
from pydantic import field_validator, model_validator


class WidgetCreate(BaseModel):
    name: str
    color: str
    quantity: int = 1

    @field_validator("name")
    @classmethod
    def normalize_name(cls, v: str) -> str:
        if v.lower() in {"admin", "system"}:
            raise ValueError("Reserved name")
        return v.strip().lower()

    @model_validator(mode="after")
    def check_quantity(self) -> "WidgetCreate":
        if self.color == "rare" and self.quantity > 1:
            raise ValueError("Rare widgets are limited to one per request")
        return self
```

`field_validator` validates one field; `model_validator(mode="after")` runs after all fields are set and can validate combinations.

### Computed Fields

For values derived at serialization time (not stored):

```python
from pydantic import computed_field


class UserReadWithStats(UserRead):
    created_at: datetime  # add this if your read schema doesn't already have it

    @computed_field
    @property
    def display_name(self) -> str:
        return f"@{self.username}"

    @computed_field
    @property
    def age_days(self) -> int:
        return (datetime.now(UTC) - self.created_at).days
```

## Multi-Record Responses

The boilerplate uses **FastCRUD's `PaginatedListResponse`** for paginated list endpoints:

```python
from fastcrud import PaginatedListResponse, compute_offset, paginated_response


@router.get("/", response_model=PaginatedListResponse[UserRead])
async def get_users(
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

The response shape:

```json
{
  "data": [{ "id": 1, "name": "...", "username": "..." }],
  "total_count": 150,
  "has_more": true,
  "page": 1,
  "items_per_page": 10
}
```

For single-record endpoints, return the schema directly:

```python
@router.get("/me", response_model=UserRead)
async def me(current_user: Annotated[dict[str, Any], Depends(get_current_user)]):
    return current_user
```

## Adding Schemas for a New Module

1. **Create the schema file**: `backend/src/modules/widgets/schemas.py`
2. **Define a `WidgetBase`** with the fields shared by create/update/read
3. **Add `WidgetCreate`, `WidgetRead`, `WidgetUpdate`** (and any internal variants you need)
4. **Wire them up** in the module's `routes.py` and `service.py`

```python
# backend/src/modules/widgets/schemas.py
from datetime import datetime
from typing import Annotated
from pydantic import BaseModel, ConfigDict, Field

from ..common.schemas import TimestampSchema


class WidgetBase(BaseModel):
    name: Annotated[str, Field(min_length=1, max_length=50)]
    description: Annotated[str | None, Field(max_length=255, default=None)]


class WidgetCreate(WidgetBase):
    model_config = ConfigDict(extra="forbid")


class WidgetRead(WidgetBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    owner_id: int
    created_at: datetime


class WidgetUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Annotated[str | None, Field(min_length=1, max_length=50, default=None)]
    description: Annotated[str | None, Field(max_length=255, default=None)]
```

## Common Pitfalls

### Don't expose sensitive fields

```python
# BAD — leaks the password hash
class UserRead(BaseModel):
    hashed_password: str

# GOOD — read-only public shape
class UserRead(BaseModel):
    id: int
    name: str
    username: str
    email: EmailStr
    profile_image_url: str
```

### Don't query the database in validators

```python
# BAD — every request hits the DB twice
@field_validator("email")
@classmethod
def email_must_be_unique(cls, v):
    if crud_users.exists(email=v):  # I/O in a validator
        raise ValueError("Email already exists")

# GOOD — let the DB unique constraint and service-layer logic handle it
```

The boilerplate's `UserService.create` already checks for duplicates before insert. The DB unique constraint is the final guardrail.

### Don't reuse the same schema for create and update

A `Create` schema requires fields that an `Update` schema should be able to omit. Splitting them avoids accidental "this field defaulted because the client forgot it" bugs.

## Next Steps

1. **[CRUD Operations](crud.md)** - How schemas plug into FastCRUD
2. **[Migrations](migrations.md)** - Manage the underlying database changes
3. **[API Endpoints](../api/endpoints.md)** - Use schemas in route handlers
