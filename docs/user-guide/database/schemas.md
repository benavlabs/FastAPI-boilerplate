# Database Schemas

This section explains how Pydantic schemas handle data validation, serialization, and API contracts in the boilerplate. Schemas are separate from SQLAlchemy models and define what data enters and exits your API.

## Schema Purpose and Structure

Schemas serve three main purposes:

1. **Input Validation** - Validate incoming API request data
2. **Output Serialization** - Format database data for API responses  
3. **API Contracts** - Define clear interfaces between frontend and backend

### Schema File Organization

Schemas are organized in `src/app/schemas/` with one file per model:

```text
src/app/schemas/
├── __init__.py       # Imports for easy access
├── user.py          # User-related schemas
├── post.py          # Post-related schemas
├── tier.py          # Tier schemas
├── rate_limit.py    # Rate limit schemas
└── job.py           # Background job schemas
```

## User Schema Implementation

The User schemas (`src/app/schemas/user.py`) demonstrate common validation patterns:

```python
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from ..core.schemas import PersistentDeletion, TimestampSchema, UUIDSchema


# Base schema with common fields
class UserBase(BaseModel):
    name: Annotated[
        str, 
        Field(
            min_length=2,
            max_length=30,
            examples=["User Userson"]
        )
    ]
    username: Annotated[
        str,
        Field(
            min_length=2,
            max_length=20,
            pattern=r"^[a-z0-9]+$",
            examples=["userson"]
        )
    ]
    email: Annotated[EmailStr, Field(examples=["user.userson@example.com"])]


# Full User data
class User(TimestampSchema, UserBase, UUIDSchema, PersistentDeletion):
    profile_image_url: Annotated[
        str,
        Field(default="https://www.profileimageurl.com")
    ]
    hashed_password: str
    is_superuser: bool = False
    tier_id: int | None = None


# Schema for reading user data (API output)
class UserRead(BaseModel):
    id: int

    name: Annotated[
        str,
        Field(
            min_length=2, 
            max_length=30, 
            examples=["User Userson"]
        )
    ]
    username: Annotated[
        str, 
        Field(
            min_length=2, 
            max_length=20, 
            pattern=r"^[a-z0-9]+$", 
            examples=["userson"]
        )
    ]
    email: Annotated[EmailStr, Field(examples=["user.userson@example.com"])]
    profile_image_url: str
    tier_id: int | None


# Schema for creating new users (API input)
class UserCreate(UserBase): # Inherits from UserBase
    model_config = ConfigDict(extra="forbid")

    password: Annotated[
        str,
        Field(
            pattern=r"^.{8,}|[0-9]+|[A-Z]+|[a-z]+|[^a-zA-Z0-9]+$",
            examples=["Str1ngst!"]
        )
    ]


# Schema that FastCRUD will use to store just the hash
class UserCreateInternal(UserBase):
    hashed_password: str


# Schema for updating users
class UserUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Annotated[
        str | None,
        Field(
            min_length=2, 
            max_length=30, 
            examples=["User Userberg"],
            default=None
        )
    ]
    username: Annotated[
        str | None, 
        Field(
            min_length=2,
            max_length=20, 
            pattern=r"^[a-z0-9]+$", 
            examples=["userberg"], 
            default=None
        )
    ]
    email: Annotated[
        EmailStr | None, 
        Field(
            examples=["user.userberg@example.com"],
            default=None
        )
    ]
    profile_image_url: Annotated[
        str | None,
        Field(
            pattern=r"^(https?|ftp)://[^\s/$.?#].[^\s]*$",
            examples=["https://www.profileimageurl.com"],
            default=None
        ),
    ]


# Internal update schema
class UserUpdateInternal(UserUpdate):
    updated_at: datetime


# Schema to update tier id
class UserTierUpdate(BaseModel):
    tier_id: int


# Schema for user deletion (soft delete timestamps)
class UserDelete(BaseModel):
    model_config = ConfigDict(extra="forbid")

    is_deleted: bool
    deleted_at: datetime


# User specific schema
class UserRestoreDeleted(BaseModel):
    is_deleted: bool
```

### Key Implementation Details

**Field Validation**: Uses `Annotated[type, Field(...)]` for validation rules. `Field` parameters include:

- `min_length/max_length` - String length constraints
- `gt/ge/lt/le` - Numeric constraints  
- `pattern` - Pattern matching (regex)
- `default` - Default values

**EmailStr**: Validates email format and normalizes the value.

**ConfigDict**: Replaces the old `Config` class. `from_attributes=True` allows creating schemas from SQLAlchemy model instances.

**Internal vs External**: Separate schemas for internal operations (like password hashing) vs API exposure.

## Schema Patterns

### Base Schema Pattern

```python
# Common fields shared across operations
class PostBase(BaseModel):
    title: Annotated[
        str, 
        Field(
            min_length=1, 
            max_length=100
        )
    ]
    content: Annotated[
        str, 
        Field(
            min_length=1, 
            max_length=10000
        )
    ]

# Specific operation schemas inherit from base
class PostCreate(PostBase):
    pass  # Only title and content needed for creation

class PostRead(PostBase):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    created_at: datetime
    created_by_user_id: int
    is_deleted: bool = False  # From model's soft delete fields
```

**Purpose**: Reduces duplication and ensures consistency across related schemas.

### Optional Fields in Updates

```python
class PostUpdate(BaseModel):
    title: Annotated[
        str | None, 
        Field(
            min_length=1, 
            max_length=100,
            default=None
        )
    ]
    content: Annotated[
        str | None, 
        Field(
            min_length=1, 
            max_length=10000,
            default=None
        )
    ]
```

**Pattern**: All fields optional in update schemas. Only provided fields are updated in the database.

### Nested Schemas

```python
# Post schema with user information
class PostWithUser(PostRead):
    created_by_user: UserRead  # Nested user data

# Alternative: Custom nested schema
class PostAuthor(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    username: str
    # Only include fields needed for this context

class PostRead(PostBase):
    created_by_user: PostAuthor
```

**Usage**: Include related model data in responses without exposing all fields.

## Validation Patterns

### Custom Validators

```python
from pydantic import field_validator, model_validator

class UserCreateWithConfirm(UserBase):
    password: str
    confirm_password: str
    
    @field_validator('username')
    @classmethod
    def validate_username(cls, v):
        if v.lower() in ['admin', 'root', 'system']:
            raise ValueError('Username not allowed')
        return v.lower()  # Normalize to lowercase
    
    @model_validator(mode='after')
    def validate_passwords_match(self):
        if self.password != self.confirm_password:
            raise ValueError('Passwords do not match')
        return self
```

**field_validator**: Validates individual fields. Can transform values.

**model_validator**: Validates across multiple fields. Access to full model data.

### Computed Fields

```python
from pydantic import computed_field

class UserReadWithComputed(UserRead):
    created_at: datetime  # Would need to be added to actual UserRead
    
    @computed_field
    @property
    def age_days(self) -> int:
        return (datetime.utcnow() - self.created_at).days
    
    @computed_field
    @property  
    def display_name(self) -> str:
        return f"@{self.username}"
```

**Purpose**: Add computed values to API responses without storing them in the database.

### Conditional Validation

```python
class PostCreate(BaseModel):
    title: str
    content: str
    category: Optional[str] = None
    is_premium: bool = False
    
    @model_validator(mode='after')
    def validate_premium_content(self):
        if self.is_premium and not self.category:
            raise ValueError('Premium posts must have a category')
        return self
```

## Schema Configuration

### Model Config Options

```python
class UserRead(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,    # Allow creation from SQLAlchemy models
        extra="forbid",          # Reject extra fields
        str_strip_whitespace=True,  # Strip whitespace from strings
        validate_assignment=True,   # Validate on field assignment
        populate_by_name=True,      # Allow field names and aliases
    )
```

### Field Aliases

```python
class UserResponse(BaseModel):
    user_id: Annotated[
        int, 
        Field(alias="id")
    ]
    username: str
    email_address: Annotated[
        str, 
        Field(alias="email")
    ]
    
    model_config = ConfigDict(populate_by_name=True)
```

**Usage**: API can accept both `id` and `user_id`, `email` and `email_address`.

## Response Schema Patterns

### Multi-Record Responses

[FastCRUD's](https://benavlabs.github.io/fastcrud/) `get_multi` method returns a `GetMultiResponse`:

```python
# Using get_multi directly
users = await crud_users.get_multi(
    db=db,
    offset=0,
    limit=10,
    schema_to_select=UserRead,
    return_as_model=True,
    return_total_count=True
)
# Returns GetMultiResponse structure:
# {
#   "data": [UserRead, ...],
#   "total_count": 150
# }
```

### Paginated Responses

For pagination with page numbers, use `PaginatedListResponse`:

```python
from fastcrud.paginated import PaginatedListResponse

# In API endpoint - ONLY for paginated list responses
@router.get("/users/", response_model=PaginatedListResponse[UserRead])
async def get_users(page: int = 1, items_per_page: int = 10):
    # Returns paginated structure with additional pagination fields:
    # {
    #   "data": [UserRead, ...],
    #   "total_count": 150,
    #   "has_more": true,
    #   "page": 1, 
    #   "items_per_page": 10
    # }

# Single user endpoints return UserRead directly
@router.get("/users/{user_id}", response_model=UserRead)
async def get_user(user_id: int):
    # Returns single UserRead object:
    # {
    #   "id": 1,
    #   "name": "User Userson", 
    #   "username": "userson",
    #   "email": "user.userson@example.com",
    #   "profile_image_url": "https://...",
    #   "tier_id": null
    # }
```

### Error Response Schemas

```python
class ErrorResponse(BaseModel):
    detail: str
    error_code: Optional[str] = None
    
class ValidationErrorResponse(BaseModel):
    detail: str
    errors: list[dict]  # Pydantic validation errors
```

### Success Response Wrapper

```python
from typing import Generic, TypeVar

T = TypeVar('T')

class SuccessResponse(BaseModel, Generic[T]):
    success: bool = True
    data: T
    message: Optional[str] = None

# Usage in endpoint
@router.post("/users/", response_model=SuccessResponse[UserRead])
async def create_user(user_data: UserCreate):
    user = await crud_users.create(db=db, object=user_data)
    return SuccessResponse(data=user, message="User created successfully")
```

## Creating New Schemas

### Step-by-Step Process

1. **Create schema file** in `src/app/schemas/your_model.py`
2. **Define base schema** with common fields
3. **Create operation-specific schemas** (Create, Read, Update, Delete)
4. **Add validation rules** as needed
5. **Import in __init__.py** for easy access

### Example: Category Schemas

```python
# src/app/schemas/category.py
from datetime import datetime
from typing import Annotated
from pydantic import BaseModel, Field, ConfigDict

class CategoryBase(BaseModel):
    name: Annotated[
        str, 
        Field(
            min_length=1, 
            max_length=50
        )
    ]
    description: Annotated[
        str | None, 
        Field(
            max_length=255,
            default=None
        )
    ]

class CategoryCreate(CategoryBase):
    pass

class CategoryRead(CategoryBase):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    created_at: datetime

class CategoryUpdate(BaseModel):
    name: Annotated[
        str | None, 
        Field(
            min_length=1, 
            max_length=50,
            default=None
        )
    ]
    description: Annotated[
        str | None, 
        Field(
            max_length=255,
            default=None
        )
    ]

class CategoryWithPosts(CategoryRead):
    posts: list[PostRead] = []  # Include related posts
```

### Import in __init__.py

```python
# src/app/schemas/__init__.py
from .user import UserCreate, UserRead, UserUpdate
from .post import PostCreate, PostRead, PostUpdate
from .category import CategoryCreate, CategoryRead, CategoryUpdate
```

## Schema Testing

### Validation Testing

```python
# tests/test_schemas.py
import pytest
from pydantic import ValidationError
from app.schemas.user import UserCreate

def test_user_create_valid():
    user_data = {
        "name": "Test User",
        "username": "testuser",
        "email": "test@example.com",
        "password": "Str1ngst!"
    }
    user = UserCreate(**user_data)
    assert user.username == "testuser"
    assert user.name == "Test User"

def test_user_create_invalid_email():
    with pytest.raises(ValidationError) as exc_info:
        UserCreate(
            name="Test User",
            username="test",
            email="invalid-email",
            password="Str1ngst!"
        )
    
    errors = exc_info.value.errors()
    assert any(error['type'] == 'value_error' for error in errors)

def test_password_validation():
    with pytest.raises(ValidationError) as exc_info:
        UserCreate(
            name="Test User",
            username="test", 
            email="test@example.com",
            password="123"  # Doesn't match pattern
        )
```

### Serialization Testing

```python
from app.models.user import User
from app.schemas.user import UserRead

def test_user_read_from_model():
    # Create model instance
    user_model = User(
        id=1,
        name="Test User",
        username="testuser",
        email="test@example.com",
        profile_image_url="https://example.com/image.jpg",
        hashed_password="hashed123",
        is_superuser=False,
        tier_id=None,
        created_at=datetime.utcnow()
    )
    
    # Convert to schema
    user_schema = UserRead.model_validate(user_model)
    assert user_schema.username == "testuser"
    assert user_schema.id == 1
    assert user_schema.name == "Test User"
    # hashed_password not included in UserRead
```

## Common Pitfalls

### Model vs Schema Field Names

```python
# DON'T - Exposing sensitive fields
class UserRead(BaseModel):
    hashed_password: str  # Never expose password hashes

# DO - Only expose safe fields  
class UserRead(BaseModel):
    id: int
    name: str
    username: str
    email: str
    profile_image_url: str
    tier_id: int | None
```

### Validation Performance

```python
# DON'T - Complex validation in every request
@field_validator('email')
@classmethod  
def validate_email_unique(cls, v):
    # Database query in validator - slow!
    if crud_users.exists(email=v):
        raise ValueError('Email already exists')

# DO - Handle uniqueness in business logic
# Let database unique constraints handle this
```

## Next Steps

Now that you understand schema implementation:

1. **[CRUD Operations](crud.md)** - Learn how schemas integrate with database operations
2. **[Migrations](migrations.md)** - Manage database schema changes
3. **[API Endpoints](../api/endpoints.md)** - Use schemas in FastAPI endpoints

The next section covers CRUD operations and how they use these schemas for data validation and transformation.