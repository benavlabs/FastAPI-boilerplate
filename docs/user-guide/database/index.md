# Database Layer

Learn how to work with the database layer in the FastAPI Boilerplate. This section covers everything you need to store and retrieve data effectively.

## What You'll Learn

- **[Models](models.md)** - Define database tables with SQLAlchemy models
- **[Schemas](schemas.md)** - Validate and serialize data with Pydantic schemas  
- **[CRUD Operations](crud.md)** - Perform database operations with FastCRUD
- **[Migrations](migrations.md)** - Manage database schema changes with Alembic

## Quick Overview

The boilerplate uses a layered architecture that separates concerns:

```python
# API Endpoint
@router.post("/", response_model=UserRead)
async def create_user(user_data: UserCreate, db: AsyncSession):
    return await crud_users.create(db=db, object=user_data)

# The layers work together:
# 1. UserCreate schema validates the input
# 2. crud_users handles the database operation  
# 3. User model defines the database table
# 4. UserRead schema formats the response
```

## Architecture

The database layer follows a clear separation:

```
API Request
    ↓
Pydantic Schema (validation & serialization)
    ↓
CRUD Layer (business logic & database operations)
    ↓
SQLAlchemy Model (database table definition)
    ↓
PostgreSQL Database
```

## Key Features

### 🗄️ **SQLAlchemy 2.0 Models**
Modern async SQLAlchemy with type hints:
```python
class User(Base):
    __tablename__ = "user"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True)
    email: Mapped[str] = mapped_column(String(100), unique=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
```

### ✅ **Pydantic Schemas**
Automatic validation and serialization:
```python
class UserCreate(BaseModel):
    username: str = Field(min_length=2, max_length=50)
    email: EmailStr
    password: str = Field(min_length=8)

class UserRead(BaseModel):
    id: int
    username: str
    email: str
    created_at: datetime
    # Note: no password field in read schema
```

### 🔧 **FastCRUD Operations**
Consistent database operations:
```python
# Create
user = await crud_users.create(db=db, object=user_create)

# Read
user = await crud_users.get(db=db, id=user_id)
users = await crud_users.get_multi(db=db, offset=0, limit=10)

# Update  
user = await crud_users.update(db=db, object=user_update, id=user_id)

# Delete (soft delete)
await crud_users.delete(db=db, id=user_id)
```

### 🔄 **Database Migrations**
Track schema changes with Alembic:
```bash
# Generate migration
alembic revision --autogenerate -m "Add user table"

# Apply migrations
alembic upgrade head

# Rollback if needed
alembic downgrade -1
```

## Database Setup

The boilerplate is configured for PostgreSQL with async support:

### Environment Configuration
```bash
# .env file
POSTGRES_USER=your_user
POSTGRES_PASSWORD=your_password
POSTGRES_SERVER=localhost
POSTGRES_PORT=5432
POSTGRES_DB=your_database
```

### Connection Management
```python
# Database session dependency
async def async_get_db() -> AsyncIterator[AsyncSession]:
    async with async_session_maker() as session:
        yield session

# Use in endpoints
@router.get("/users/")
async def get_users(db: Annotated[AsyncSession, Depends(async_get_db)]):
    return await crud_users.get_multi(db=db)
```

## Included Models

The boilerplate includes four example models:

### **User Model** - Authentication & user management
- Username, email, password (hashed)
- Soft delete support
- Tier-based access control

### **Post Model** - Content with user relationships  
- Title, content, creation metadata
- Foreign key to user (no SQLAlchemy relationships)
- Soft delete built-in

### **Tier Model** - User subscription levels
- Name-based tiers (free, premium, etc.)
- Links to rate limiting system

### **Rate Limit Model** - API access control
- Path-specific rate limits per tier
- Configurable limits and time periods

## Directory Structure

```text
src/app/
├── models/                 # SQLAlchemy models (database tables)
│   ├── __init__.py        
│   ├── user.py           # User table definition
│   ├── post.py           # Post table definition
│   └── ...
├── schemas/                # Pydantic schemas (validation)
│   ├── __init__.py
│   ├── user.py           # User validation schemas
│   ├── post.py           # Post validation schemas  
│   └── ...
├── crud/                   # Database operations
│   ├── __init__.py
│   ├── crud_users.py     # User CRUD operations
│   ├── crud_posts.py     # Post CRUD operations
│   └── ...
└── core/db/               # Database configuration
    ├── database.py       # Connection and session setup
    └── models.py         # Base classes and mixins
```

## Common Patterns

### Create with Validation
```python
@router.post("/users/", response_model=UserRead)
async def create_user(
    user_data: UserCreate,  # Validates input automatically
    db: Annotated[AsyncSession, Depends(async_get_db)]
):
    # Check for duplicates
    if await crud_users.exists(db=db, email=user_data.email):
        raise DuplicateValueException("Email already exists")
    
    # Create user (password gets hashed automatically)
    return await crud_users.create(db=db, object=user_data)
```

### Query with Filters
```python
# Get active users only
users = await crud_users.get_multi(
    db=db,
    is_active=True,
    is_deleted=False,
    offset=0,
    limit=10
)

# Search users
users = await crud_users.get_multi(
    db=db,
    username__icontains="john",  # Contains "john"
    schema_to_select=UserRead
)
```

### Soft Delete Pattern
```python
# Soft delete (sets is_deleted=True)
await crud_users.delete(db=db, id=user_id)

# Hard delete (actually removes from database)
await crud_users.db_delete(db=db, id=user_id)

# Get only non-deleted records
users = await crud_users.get_multi(db=db, is_deleted=False)
```

## What's Next

Each guide builds on the previous one with practical examples:

1. **[Models](models.md)** - Define your database structure
2. **[Schemas](schemas.md)** - Add validation and serialization
3. **[CRUD Operations](crud.md)** - Implement business logic
4. **[Migrations](migrations.md)** - Deploy changes safely

The boilerplate provides a solid foundation - just follow these patterns to build your data layer!