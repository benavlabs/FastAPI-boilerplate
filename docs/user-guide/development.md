# Development Guide

This guide covers everything you need to know about extending, customizing, and developing with the FastAPI boilerplate.

## Extending the Boilerplate

### Adding New Models

Follow this step-by-step process to add new entities to your application:

#### 1. Create SQLAlchemy Model

Create a new file in `src/app/models/` (e.g., `category.py`):

```python
from sqlalchemy import String, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..core.db.database import Base


class Category(Base):
    __tablename__ = "category"

    id: Mapped[int] = mapped_column(
        "id", 
        autoincrement=True, 
        nullable=False, 
        unique=True, 
        primary_key=True, 
        init=False
    )
    name: Mapped[str] = mapped_column(String(50))
    description: Mapped[str | None] = mapped_column(String(255), default=None)
    
    # Relationships
    posts: Mapped[list["Post"]] = relationship(back_populates="category")
```

#### 2. Create Pydantic Schemas

Create `src/app/schemas/category.py`:

```python
from datetime import datetime
from typing import Annotated
from pydantic import BaseModel, Field, ConfigDict


class CategoryBase(BaseModel):
    name: Annotated[str, Field(min_length=1, max_length=50)]
    description: Annotated[str | None, Field(max_length=255, default=None)]


class CategoryCreate(CategoryBase):
    model_config = ConfigDict(extra="forbid")


class CategoryRead(CategoryBase):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    created_at: datetime


class CategoryUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    
    name: Annotated[str | None, Field(min_length=1, max_length=50, default=None)]
    description: Annotated[str | None, Field(max_length=255, default=None)]


class CategoryUpdateInternal(CategoryUpdate):
    updated_at: datetime


class CategoryDelete(BaseModel):
    model_config = ConfigDict(extra="forbid")
    
    is_deleted: bool
    deleted_at: datetime
```

#### 3. Create CRUD Operations

Create `src/app/crud/crud_categories.py`:

```python
from fastcrud import FastCRUD

from ..models.category import Category
from ..schemas.category import CategoryCreate, CategoryUpdate, CategoryUpdateInternal, CategoryDelete

CRUDCategory = FastCRUD[Category, CategoryCreate, CategoryUpdate, CategoryUpdateInternal, CategoryDelete]
crud_categories = CRUDCategory(Category)
```

#### 4. Update Model Imports

Add your new model to `src/app/models/__init__.py`:

```python
from .category import Category
from .user import User
from .post import Post
# ... other imports
```

#### 5. Create Database Migration

Generate and apply the migration:

```bash
# From the src/ directory
uv run alembic revision --autogenerate -m "Add category model"
uv run alembic upgrade head
```

#### 6. Create API Endpoints

Create `src/app/api/v1/categories.py`:

```python
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastcrud.paginated import PaginatedListResponse, compute_offset
from sqlalchemy.ext.asyncio import AsyncSession

from ...api.dependencies import get_current_superuser, get_current_user
from ...core.db.database import async_get_db
from ...core.exceptions.http_exceptions import DuplicateValueException, NotFoundException
from ...crud.crud_categories import crud_categories
from ...schemas.category import CategoryCreate, CategoryRead, CategoryUpdate

router = APIRouter(tags=["categories"])


@router.post("/category", response_model=CategoryRead, status_code=201)
async def write_category(
    request: Request,
    category: CategoryCreate,
    current_user: Annotated[dict, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(async_get_db)],
):
    category_row = await crud_categories.exists(db=db, name=category.name)
    if category_row:
        raise DuplicateValueException("Category name already exists")

    return await crud_categories.create(db=db, object=category)


@router.get("/categories", response_model=PaginatedListResponse[CategoryRead])
async def read_categories(
    request: Request,
    db: Annotated[AsyncSession, Depends(async_get_db)],
    page: int = 1,
    items_per_page: int = 10,
):
    categories_data = await crud_categories.get_multi(
        db=db,
        offset=compute_offset(page, items_per_page),
        limit=items_per_page,
        schema_to_select=CategoryRead,
        is_deleted=False,
    )

    return categories_data


@router.get("/category/{category_id}", response_model=CategoryRead)
async def read_category(
    request: Request,
    category_id: int,
    db: Annotated[AsyncSession, Depends(async_get_db)],
):
    db_category = await crud_categories.get(
        db=db, 
        schema_to_select=CategoryRead, 
        id=category_id,
        is_deleted=False
    )
    if not db_category:
        raise NotFoundException("Category not found")

    return db_category


@router.patch("/category/{category_id}", response_model=CategoryRead)
async def patch_category(
    request: Request,
    category_id: int,
    values: CategoryUpdate,
    current_user: Annotated[dict, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(async_get_db)],
):
    db_category = await crud_categories.get(db=db, id=category_id, is_deleted=False)
    if not db_category:
        raise NotFoundException("Category not found")

    if values.name:
        category_row = await crud_categories.exists(db=db, name=values.name)
        if category_row and category_row["id"] != category_id:
            raise DuplicateValueException("Category name already exists")

    return await crud_categories.update(db=db, object=values, id=category_id)


@router.delete("/category/{category_id}")
async def erase_category(
    request: Request,
    category_id: int,
    current_user: Annotated[dict, Depends(get_current_superuser)],
    db: Annotated[AsyncSession, Depends(async_get_db)],
):
    db_category = await crud_categories.get(db=db, id=category_id, is_deleted=False)
    if not db_category:
        raise NotFoundException("Category not found")

    await crud_categories.delete(db=db, db_row=db_category, garbage_collection=False)
    return {"message": "Category deleted"}
```

#### 7. Register Router

Add your router to `src/app/api/v1/__init__.py`:

```python
from fastapi import APIRouter
from .categories import router as categories_router
# ... other imports

router = APIRouter()
router.include_router(categories_router, prefix="/categories")
# ... other router includes
```

### Creating Custom Middleware

Create middleware in `src/app/middleware/`:

```python
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware


class CustomHeaderMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Pre-processing
        start_time = time.time()
        
        # Process request
        response = await call_next(request)
        
        # Post-processing
        process_time = time.time() - start_time
        response.headers["X-Process-Time"] = str(process_time)
        
        return response
```

Register in `src/app/main.py`:

```python
from .middleware.custom_header_middleware import CustomHeaderMiddleware

app.add_middleware(CustomHeaderMiddleware)
```

## Testing

### Test Configuration

The boilerplate uses pytest for testing. Test configuration is in `pytest.ini` and test dependencies in `pyproject.toml`.

### Database Testing Setup

Create test database fixtures in `tests/conftest.py`:

```python
import asyncio
import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from src.app.core.config import settings
from src.app.core.db.database import Base, async_get_db
from src.app.main import app

# Test database URL
TEST_DATABASE_URL = "postgresql+asyncpg://test_user:test_pass@localhost:5432/test_db"

# Create test engine
test_engine = create_async_engine(TEST_DATABASE_URL, echo=True)
TestSessionLocal = sessionmaker(
    test_engine, class_=AsyncSession, expire_on_commit=False
)


@pytest_asyncio.fixture
async def async_session():
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    async with TestSessionLocal() as session:
        yield session
    
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def async_client(async_session):
    def get_test_db():
        return async_session
    
    app.dependency_overrides[async_get_db] = get_test_db
    
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client
    
    app.dependency_overrides.clear()
```

### Writing Tests

#### Model Tests

```python
# tests/test_models.py
import pytest
from src.app.models.user import User


@pytest_asyncio.fixture
async def test_user(async_session):
    user = User(
        name="Test User",
        username="testuser",
        email="test@example.com",
        hashed_password="hashed_password"
    )
    async_session.add(user)
    await async_session.commit()
    await async_session.refresh(user)
    return user


async def test_user_creation(test_user):
    assert test_user.name == "Test User"
    assert test_user.username == "testuser"
    assert test_user.email == "test@example.com"
```

#### API Endpoint Tests

```python
# tests/test_api.py
import pytest
from httpx import AsyncClient


async def test_create_user(async_client: AsyncClient):
    user_data = {
        "name": "New User",
        "username": "newuser",
        "email": "new@example.com",
        "password": "SecurePass123!"
    }
    
    response = await async_client.post("/api/v1/users", json=user_data)
    assert response.status_code == 201
    
    data = response.json()
    assert data["name"] == "New User"
    assert data["username"] == "newuser"
    assert "hashed_password" not in data  # Ensure password not exposed


async def test_read_users(async_client: AsyncClient):
    response = await async_client.get("/api/v1/users")
    assert response.status_code == 200
    
    data = response.json()
    assert "data" in data
    assert "total_count" in data
```

#### CRUD Tests

```python
# tests/test_crud.py
import pytest
from src.app.crud.crud_users import crud_users
from src.app.schemas.user import UserCreate


async def test_crud_create_user(async_session):
    user_data = UserCreate(
        name="CRUD User",
        username="cruduser",
        email="crud@example.com",
        password="password123"
    )
    
    user = await crud_users.create(db=async_session, object=user_data)
    assert user["name"] == "CRUD User"
    assert user["username"] == "cruduser"


async def test_crud_get_user(async_session, test_user):
    retrieved_user = await crud_users.get(
        db=async_session, 
        id=test_user.id
    )
    assert retrieved_user["name"] == test_user.name
```

### Running Tests

```bash
# Run all tests
uv run pytest

# Run with coverage
uv run pytest --cov=src

# Run specific test file
uv run pytest tests/test_api.py

# Run with verbose output
uv run pytest -v

# Run tests matching pattern
uv run pytest -k "test_user"
```

## Customization

### Environment-Specific Configuration

Create environment-specific settings:

```python
# src/app/core/config.py
class LocalSettings(Settings):
    ENVIRONMENT: str = "local"
    DEBUG: bool = True
    
class ProductionSettings(Settings):
    ENVIRONMENT: str = "production"
    DEBUG: bool = False
    # Production-specific settings

def get_settings():
    env = os.getenv("ENVIRONMENT", "local")
    if env == "production":
        return ProductionSettings()
    return LocalSettings()

settings = get_settings()
```

### Custom Logging

Configure logging in `src/app/core/config.py`:

```python
import logging
from pythonjsonlogger import jsonlogger

def setup_logging():
    # JSON logging for production
    if settings.ENVIRONMENT == "production":
        logHandler = logging.StreamHandler()
        formatter = jsonlogger.JsonFormatter()
        logHandler.setFormatter(formatter)
        logger = logging.getLogger()
        logger.addHandler(logHandler)
        logger.setLevel(logging.INFO)
    else:
        # Simple logging for development
        logging.basicConfig(
            level=logging.DEBUG,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
```

## Opting Out of Services

### Disabling Redis Caching

1. Remove cache decorators from endpoints
2. Update dependencies in `src/app/core/config.py`:

```python
class Settings(BaseSettings):
    # Comment out or remove Redis cache settings
    # REDIS_CACHE_HOST: str = "localhost"
    # REDIS_CACHE_PORT: int = 6379
    pass
```

3. Remove Redis cache imports and usage

### Disabling Background Tasks (ARQ)

1. Remove ARQ from `pyproject.toml` dependencies
2. Remove worker configuration from `docker-compose.yml`
3. Delete `src/app/core/worker/` directory
4. Remove task-related endpoints

### Disabling Rate Limiting

1. Remove rate limiting dependencies from endpoints:

```python
# Remove this dependency
dependencies=[Depends(rate_limiter_dependency)]
```

2. Remove rate limiting models and schemas
3. Update database migrations to remove rate limit tables

### Disabling Authentication

1. Remove JWT dependencies from protected endpoints
2. Remove user-related models and endpoints
3. Update database to remove user tables
4. Remove authentication middleware

### Minimal FastAPI Setup

For a minimal setup with just basic FastAPI:

```python
# src/app/main.py (minimal version)
from fastapi import FastAPI

app = FastAPI(
    title="Minimal API",
    description="Basic FastAPI application",
    version="1.0.0"
)

@app.get("/")
async def root():
    return {"message": "Hello World"}

@app.get("/health")
async def health_check():
    return {"status": "healthy"}
```

## Best Practices

### Code Organization

- Keep models, schemas, and CRUD operations in separate files
- Use consistent naming conventions across the application
- Group related functionality in modules
- Follow FastAPI and Pydantic best practices

### Database Operations

- Always use transactions for multi-step operations
- Implement soft deletes for important data
- Use database constraints for data integrity
- Index frequently queried columns

### API Design

- Use consistent response formats
- Implement proper error handling
- Version your APIs from the start
- Document all endpoints with proper schemas

### Security

- Never expose sensitive data in API responses
- Use proper authentication and authorization
- Validate all input data
- Implement rate limiting for public endpoints
- Use HTTPS in production

### Performance

- Use async/await consistently
- Implement caching for expensive operations
- Use database connection pooling
- Monitor and optimize slow queries
- Use pagination for large datasets

## Troubleshooting

### Common Issues

**Import Errors**: Ensure all new models are imported in `__init__.py` files

**Migration Failures**: Check model definitions and relationships before generating migrations

**Test Failures**: Verify test database configuration and isolation

**Performance Issues**: Check for N+1 queries and missing database indexes

**Authentication Problems**: Verify JWT configuration and token expiration settings

### Debugging Tips

- Use FastAPI's automatic interactive docs at `/docs`
- Enable SQL query logging in development
- Use proper logging throughout the application
- Test endpoints with realistic data volumes
- Monitor database performance with query analysis

## Database Migrations

!!! warning "Important Setup for Docker Users"
    If you're using the database in Docker, you need to expose the port to run migrations. Change this in `docker-compose.yml`:

    ```yaml
    db:
      image: postgres:13
      env_file:
        - ./src/.env
      volumes:
        - postgres-data:/var/lib/postgresql/data
      # -------- replace with comment to run migrations with docker --------
      ports:
        - 5432:5432
      # expose:
      #   - "5432"
    ```

### Creating Migrations

!!! warning "Model Import Requirement"
    To create tables if you haven't created endpoints yet, ensure you import the models in `src/app/models/__init__.py`. This step is crucial for Alembic to detect new tables.

While in the `src` folder, run Alembic migrations:

```bash
# Generate migration file
uv run alembic revision --autogenerate -m "Description of changes"

# Apply migrations
uv run alembic upgrade head
```

!!! note "Without uv"
    If you don't have uv, run `pip install alembic` first, then use `alembic` commands directly.

### Migration Workflow

1. **Make Model Changes** - Modify your SQLAlchemy models
2. **Import Models** - Ensure models are imported in `src/app/models/__init__.py`
3. **Generate Migration** - Run `alembic revision --autogenerate`
4. **Review Migration** - Check the generated migration file in `src/migrations/versions/`
5. **Apply Migration** - Run `alembic upgrade head`
6. **Test Changes** - Verify your changes work as expected

### Common Migration Tasks

#### Adding a New Model

```python
# 1. Create the model file (e.g., src/app/models/category.py)
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db.database import Base

class Category(Base):
    __tablename__ = "categories"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50))
    description: Mapped[str] = mapped_column(String(255), nullable=True)
```

```python
# 2. Import in src/app/models/__init__.py
from .user import User
from .post import Post
from .tier import Tier
from .rate_limit import RateLimit
from .category import Category  # Add this line
```

```bash
# 3. Generate and apply migration
cd src
uv run alembic revision --autogenerate -m "Add categories table"
uv run alembic upgrade head
```

#### Modifying Existing Models

```python
# 1. Modify your model
class User(Base):
    # ... existing fields ...
    bio: Mapped[str] = mapped_column(String(500), nullable=True)  # New field
```

```bash
# 2. Generate migration
uv run alembic revision --autogenerate -m "Add bio field to users"

# 3. Review the generated migration file
# 4. Apply migration
uv run alembic upgrade head
```

This guide provides the foundation for extending and customizing the FastAPI boilerplate. For specific implementation details, refer to the existing code examples throughout the boilerplate. 