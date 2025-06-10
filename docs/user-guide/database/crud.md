# CRUD Operations

This guide covers all CRUD (Create, Read, Update, Delete) operations available in the FastAPI Boilerplate using FastCRUD, a powerful library that provides consistent and efficient database operations.

## Overview

The boilerplate uses [FastCRUD](https://github.com/igorbenav/fastcrud) for all database operations. FastCRUD provides:

- **Consistent API** across all models
- **Type safety** with generic type parameters
- **Automatic pagination** support
- **Advanced filtering** and joining capabilities
- **Soft delete** support
- **Optimized queries** with selective field loading

## CRUD Class Structure

Each model has a corresponding CRUD class that defines the available operations:

```python
# src/app/crud/crud_users.py
from fastcrud import FastCRUD
from app.models.user import User
from app.schemas.user import (
    UserCreateInternal, UserUpdate, UserUpdateInternal, 
    UserDelete, UserRead
)

CRUDUser = FastCRUD[
    User,                # Model class
    UserCreateInternal,  # Create schema
    UserUpdate,          # Update schema  
    UserUpdateInternal,  # Internal update schema
    UserDelete,          # Delete schema
    UserRead             # Read schema
]
crud_users = CRUDUser(User)
```

## Read Operations

### Get Single Record

Retrieve a single record by any field:

```python
# Get user by ID
user = await crud_users.get(db=db, id=user_id)

# Get user by username
user = await crud_users.get(db=db, username="john_doe")

# Get user by email
user = await crud_users.get(db=db, email="john@example.com")

# Get with specific fields only
user = await crud_users.get(
    db=db, 
    schema_to_select=UserRead, # Only select fields defined in UserRead
    id=user_id,
)
```

**Real usage from the codebase:**

```python
# From src/app/api/v1/users.py
db_user = await crud_users.get(
    db=db, 
    schema_to_select=UserRead,
    username=username, 
    is_deleted=False,
)
```

### Get Multiple Records

Retrieve multiple records with filtering and pagination:

```python
# Get all users
users = await crud_users.get_multi(db=db)

# Get with pagination
users = await crud_users.get_multi(
    db=db,
    offset=0,      # Skip first 0 records
    limit=10,      # Return maximum 10 records
)

# Get with filtering
active_users = await crud_users.get_multi(
    db=db,
    is_deleted=False,  # Filter condition
    offset=compute_offset(page, items_per_page),
    limit=items_per_page
)
```

**Pagination response structure:**

```python
{
    "data": [
        {"id": 1, "username": "john", "email": "john@example.com"},
        {"id": 2, "username": "jane", "email": "jane@example.com"}
    ],
    "total_count": 25,
    "has_more": true,
    "page": 1,
    "items_per_page": 10
}
```

### Check Existence

Check if a record exists without fetching it:

```python
# Check if user exists
user_exists = await crud_users.exists(db=db, email="john@example.com")
# Returns True or False

# Check if username is available
username_taken = await crud_users.exists(db=db, username="john_doe")
```

**Real usage example:**

```python
# From src/app/api/v1/users.py - checking before creating
email_row = await crud_users.exists(db=db, email=user.email)
if email_row:
    raise DuplicateValueException("Email is already registered")
```

### Count Records

Get count of records matching criteria:

```python
# Count all users
total_users = await crud_users.count(db=db)

# Count active users
active_count = await crud_users.count(db=db, is_deleted=False)

# Count by specific criteria
admin_count = await crud_users.count(db=db, is_superuser=True)
```

## Create Operations

### Basic Creation

Create new records using Pydantic schemas:

```python
# Create user
user_data = UserCreateInternal(
    username="john_doe",
    email="john@example.com", 
    hashed_password="hashed_password_here"
)

created_user = await crud_users.create(db=db, object=user_data)
```

**Real creation example:**

```python
# From src/app/api/v1/users.py
user_internal_dict = user.model_dump()
user_internal_dict["hashed_password"] = get_password_hash(password=user_internal_dict["password"])
del user_internal_dict["password"]

user_internal = UserCreateInternal(**user_internal_dict)
created_user = await crud_users.create(db=db, object=user_internal)
```

### Create with Relationships

When creating records with foreign keys:

```python
# Create post for a user
post_data = PostCreateInternal(
    title="My First Post",
    content="This is the content of my post",
    created_by_user_id=user.id  # Foreign key reference
)

created_post = await crud_posts.create(db=db, object=post_data)
```

## Update Operations

### Basic Updates

Update records by any field:

```python
# Update user by ID
update_data = UserUpdate(email="newemail@example.com")
await crud_users.update(db=db, object=update_data, id=user_id)

# Update by username
await crud_users.update(db=db, object=update_data, username="john_doe")

# Update multiple fields
update_data = UserUpdate(
    email="newemail@example.com",
    profile_image_url="https://newimage.com/photo.jpg"
)
await crud_users.update(db=db, object=update_data, id=user_id)
```

### Conditional Updates

Update with validation:

```python
# From real endpoint - check before updating
if values.username != db_user.username:
    existing_username = await crud_users.exists(db=db, username=values.username)
    if existing_username:
        raise DuplicateValueException("Username not available")

await crud_users.update(db=db, object=values, username=username)
```

### Bulk Updates

Update multiple records at once:

```python
# Update all users with specific criteria
update_data = {"is_active": False}
await crud_users.update(db=db, object=update_data, is_deleted=True)
```

## Delete Operations

### Soft Delete

For models with soft delete fields (like User, Post):

```python
# Soft delete - sets is_deleted=True, deleted_at=now()
await crud_users.delete(db=db, username="john_doe")

# The record stays in the database but is marked as deleted
user = await crud_users.get(db=db, username="john_doe", is_deleted=True)
```

### Hard Delete

Permanently remove records from the database:

```python
# Permanently delete from database
await crud_users.db_delete(db=db, username="john_doe")

# The record is completely removed
```

**Real deletion example:**

```python
# From src/app/api/v1/users.py
# Regular users get soft delete
await crud_users.delete(db=db, username=username)

# Superusers can hard delete
await crud_users.db_delete(db=db, username=username)
```

## Advanced Operations

### Joined Queries

Get data from multiple related tables:

```python
# Get posts with user information
posts_with_users = await crud_posts.get_multi_joined(
    db=db,
    join_model=User,
    join_on=Post.created_by_user_id == User.id,
    schema_to_select=PostRead,
    join_schema_to_select=UserRead,
    join_prefix="user_"
)
```

Result structure:
```python
{
    "id": 1,
    "title": "My Post",
    "content": "Post content",
    "user_id": 123,
    "user_username": "john_doe",
    "user_email": "john@example.com"
}
```

### Custom Filtering

Advanced filtering with SQLAlchemy expressions:

```python
from sqlalchemy import and_, or_

# Complex filters
users = await crud_users.get_multi(
    db=db,
    filter_criteria=[
        and_(
            User.is_deleted == False,
            User.created_at > datetime(2024, 1, 1)
        )
    ]
)
```

### Optimized Field Selection

Select only needed fields for better performance:

```python
# Only select id and username
users = await crud_users.get_multi(
    db=db,
    schema_to_select=UserRead,  # Use schema to define fields
    limit=100
)

# Or specify fields directly
users = await crud_users.get_multi(
    db=db,
    schema_to_select=["id", "username", "email"],
    limit=100
)
```

## Practical Examples

### Complete CRUD Workflow

Here's a complete example showing all CRUD operations:

```python
from sqlalchemy.ext.asyncio import AsyncSession
from app.crud.crud_users import crud_users
from app.schemas.user import UserCreateInternal, UserUpdate, UserRead

async def user_management_example(db: AsyncSession):
    # 1. CREATE
    user_data = UserCreateInternal(
        username="demo_user",
        email="demo@example.com",
        hashed_password="hashed_password"
    )
    new_user = await crud_users.create(db=db, object=user_data)
    print(f"Created user: {new_user.id}")
    
    # 2. READ
    user = await crud_users.get(
        db=db, 
        id=new_user.id, 
        schema_to_select=UserRead
    )
    print(f"Retrieved user: {user.username}")
    
    # 3. UPDATE  
    update_data = UserUpdate(email="updated@example.com")
    await crud_users.update(db=db, object=update_data, id=new_user.id)
    print("User updated")
    
    # 4. DELETE (soft delete)
    await crud_users.delete(db=db, id=new_user.id)
    print("User soft deleted")
    
    # 5. VERIFY DELETION
    deleted_user = await crud_users.get(db=db, id=new_user.id, is_deleted=True)
    print(f"User deleted at: {deleted_user.deleted_at}")
```

### Pagination Helper

Using FastCRUD's pagination utilities:

```python
from fastcrud.paginated import compute_offset, paginated_response

async def get_paginated_users(
    db: AsyncSession, 
    page: int = 1, 
    items_per_page: int = 10
):
    users_data = await crud_users.get_multi(
        db=db,
        offset=compute_offset(page, items_per_page),
        limit=items_per_page,
        is_deleted=False,
        schema_to_select=UserRead
    )
    
    return paginated_response(
        crud_data=users_data, 
        page=page, 
        items_per_page=items_per_page
    )
```

### Error Handling

Proper error handling with CRUD operations:

```python
from app.core.exceptions.http_exceptions import NotFoundException, DuplicateValueException

async def safe_user_creation(db: AsyncSession, user_data: UserCreate):
    # Check for duplicates
    if await crud_users.exists(db=db, email=user_data.email):
        raise DuplicateValueException("Email already registered")
    
    if await crud_users.exists(db=db, username=user_data.username):
        raise DuplicateValueException("Username not available")
    
    # Create user
    try:
        user_internal = UserCreateInternal(**user_data.model_dump())
        created_user = await crud_users.create(db=db, object=user_internal)
        return created_user
    except Exception as e:
        # Handle database errors
        await db.rollback()
        raise e
```

## Performance Tips

### 1. Use Schema Selection

Always specify `schema_to_select` to avoid loading unnecessary data:

```python
# Good - only loads needed fields
user = await crud_users.get(db=db, id=user_id, schema_to_select=UserRead)

# Avoid - loads all fields
user = await crud_users.get(db=db, id=user_id)
```

### 2. Batch Operations

For multiple operations, use transactions:

```python
async def batch_user_updates(db: AsyncSession, updates: List[dict]):
    try:
        for update in updates:
            await crud_users.update(db=db, object=update["data"], id=update["id"])
        await db.commit()
    except Exception:
        await db.rollback()
        raise
```

### 3. Use Exists for Checks

Use `exists()` instead of `get()` when you only need to check existence:

```python
# Good - faster, doesn't load data
if await crud_users.exists(db=db, email=email):
    raise DuplicateValueException("Email taken")

# Avoid - slower, loads unnecessary data
user = await crud_users.get(db=db, email=email)
if user:
    raise DuplicateValueException("Email taken")
```

## Next Steps

- **[Database Migrations](migrations.md)** - Managing database schema changes
- **[API Development](../api/index.md)** - Using CRUD in API endpoints
- **[Caching](../caching/index.md)** - Optimizing CRUD with caching 