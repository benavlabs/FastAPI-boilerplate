# First Run Guide

Congratulations on setting up the FastAPI Boilerplate! This guide will walk you through testing your installation, understanding the basics, and making your first customizations.

## Verification Checklist

Before diving deeper, let's verify everything is working correctly.

### 1. Check All Services

Ensure all services are running:

```bash
# For Docker Compose users
docker compose ps

# Expected output:
# NAME                          COMMAND                  SERVICE   STATUS
# fastapi-boilerplate-web-1     "uvicorn app.main:app…"  web       running
# fastapi-boilerplate-db-1      "docker-entrypoint.s…"  db        running
# fastapi-boilerplate-redis-1   "docker-entrypoint.s…"  redis     running
# fastapi-boilerplate-worker-1  "arq src.app.core.wo…"  worker    running
```

### 2. Test API Endpoints

Visit these URLs to confirm your API is working:

**API Documentation:**
- **Swagger UI**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc**: [http://localhost:8000/redoc](http://localhost:8000/redoc)

**Health Check:**
```bash
curl http://localhost:8000/api/v1/health
```

Expected response:
```json
{
  "status": "healthy",
  "timestamp": "2024-01-01T12:00:00Z"
}
```

### 3. Database Connection

Check if the database tables were created:

```bash
# For Docker Compose
docker compose exec db psql -U postgres -d myapp -c "\dt"

# You should see tables like:
# public | users        | table | postgres
# public | posts        | table | postgres
# public | tiers        | table | postgres
# public | rate_limits  | table | postgres
```

### 4. Redis Connection

Test Redis connectivity:

```bash
# For Docker Compose
docker compose exec redis redis-cli ping

# Expected response: PONG
```

## Initial Setup

Before testing features, you need to create the first superuser and tier.

### Creating the First Superuser

!!! warning "Prerequisites"
    Make sure the database and tables are created before running create_superuser. The database should be running and the API should have started at least once.

#### Using Docker Compose

If using Docker Compose, uncomment this section in your `docker-compose.yml`:

```yaml
#-------- uncomment to create first superuser --------
create_superuser:
  build:
    context: .
    dockerfile: Dockerfile
  env_file:
    - ./src/.env
  depends_on:
    - db
  command: python -m src.scripts.create_first_superuser
  volumes:
    - ./src:/code/src
```

Then run:

```bash
# Start services and run create_superuser automatically
docker compose up -d

# Or run it manually
docker compose run --rm create_superuser

# Stop the create_superuser service when done
docker compose stop create_superuser
```

#### From Scratch

If running manually, use:

```bash
# Make sure you're in the root folder
uv run python -m src.scripts.create_first_superuser
```

### Creating the First Tier

!!! warning "Prerequisites"
    Make sure the database and tables are created before running create_tier.

#### Using Docker Compose

Uncomment the `create_tier` service in `docker-compose.yml` and run:

```bash
docker compose run --rm create_tier
```

#### From Scratch

```bash
# Make sure you're in the root folder
uv run python -m src.scripts.create_first_tier
```

## Testing Core Features

Let's test the main features of your API.

### Authentication Flow

#### 1. Login with Admin User

Use the admin credentials you set in your `.env` file:

```bash
curl -X POST "http://localhost:8000/api/v1/login" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin&password=your_admin_password"
```

You should receive a response like:
```json
{
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
  "token_type": "bearer",
  "refresh_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9..."
}
```

#### 2. Create a New User

```bash
curl -X POST "http://localhost:8000/api/v1/users" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "John Doe",
    "username": "johndoe", 
    "email": "john@example.com",
    "password": "securepassword123"
  }'
```

#### 3. Test Protected Endpoint

Use the access token from step 1:

```bash
curl -X GET "http://localhost:8000/api/v1/users/me" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN_HERE"
```

### CRUD Operations

#### 1. Create a Post

```bash
curl -X POST "http://localhost:8000/api/v1/posts" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN_HERE" \
  -d '{
    "title": "My First Post",
    "content": "This is the content of my first post!"
  }'
```

#### 2. Get All Posts

```bash
curl -X GET "http://localhost:8000/api/v1/posts" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN_HERE"
```

#### 3. Get Posts with Pagination

```bash
curl -X GET "http://localhost:8000/api/v1/posts?page=1&items_per_page=5" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN_HERE"
```

### Background Tasks

Test the job queue system:

#### 1. Submit a Background Task

```bash
curl -X POST "http://localhost:8000/api/v1/tasks/task?message=hello" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN_HERE"
```

Response:
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000"
}
```

#### 2. Check Task Status

```bash
curl -X GET "http://localhost:8000/api/v1/tasks/task/550e8400-e29b-41d4-a716-446655440000" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN_HERE"
```

### Caching

Test the caching system:

#### 1. Make a Cached Request

```bash
# First request (cache miss)
curl -X GET "http://localhost:8000/api/v1/users/johndoe" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN_HERE" \
  -w "Time: %{time_total}s\n"

# Second request (cache hit - should be faster)
curl -X GET "http://localhost:8000/api/v1/users/johndoe" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN_HERE" \
  -w "Time: %{time_total}s\n"
```

## Your First Customization

Let's create a simple custom endpoint to see how easy it is to extend the boilerplate.

### 1. Create a Simple Model

Create `src/app/models/item.py`:

```python
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db.database import Base


class Item(Base):
    __tablename__ = "items"

    id: Mapped[int] = mapped_column("id", autoincrement=True, nullable=False, unique=True, primary_key=True, init=False)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(String(500), default="")
```

### 2. Create Pydantic Schemas

Create `src/app/schemas/item.py`:

```python
from pydantic import BaseModel, Field


class ItemBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: str = Field("", max_length=500)


class ItemCreate(ItemBase):
    pass


class ItemCreateInternal(ItemCreate):
    pass


class ItemRead(ItemBase):
    id: int


class ItemUpdate(BaseModel):
    name: str | None = None
    description: str | None = None


class ItemUpdateInternal(ItemUpdate):
    pass


class ItemDelete(BaseModel):
    is_deleted: bool = True
```

### 3. Create CRUD Operations

Create `src/app/crud/crud_items.py`:

```python
from fastcrud import FastCRUD

from app.models.item import Item
from app.schemas.item import ItemCreateInternal, ItemUpdate, ItemUpdateInternal, ItemDelete

CRUDItem = FastCRUD[Item, ItemCreateInternal, ItemUpdate, ItemUpdateInternal, ItemDelete]
crud_items = CRUDItem(Item)
```

### 4. Create API Endpoints

Create `src/app/api/v1/items.py`:

```python
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.core.db.database import async_get_db
from app.crud.crud_items import crud_items
from app.schemas.item import ItemCreate, ItemRead, ItemUpdate
from app.schemas.user import UserRead

router = APIRouter(tags=["items"])


@router.post("/", response_model=ItemRead, status_code=201)
async def create_item(
    item: ItemCreate,
    db: Annotated[AsyncSession, Depends(async_get_db)],
    current_user: Annotated[UserRead, Depends(get_current_user)]
):
    """Create a new item."""
    db_item = await crud_items.create(db=db, object=item)
    return db_item


@router.get("/{item_id}", response_model=ItemRead)
async def get_item(
    item_id: int,
    db: Annotated[AsyncSession, Depends(async_get_db)]
):
    """Get an item by ID."""
    db_item = await crud_items.get(db=db, id=item_id)
    if not db_item:
        raise HTTPException(status_code=404, detail="Item not found")
    return db_item


@router.get("/", response_model=list[ItemRead])
async def get_items(
    db: Annotated[AsyncSession, Depends(async_get_db)],
    skip: int = 0,
    limit: int = 100
):
    """Get all items."""
    items = await crud_items.get_multi(db=db, offset=skip, limit=limit)
    return items["data"]


@router.patch("/{item_id}", response_model=ItemRead)
async def update_item(
    item_id: int,
    item_update: ItemUpdate,
    db: Annotated[AsyncSession, Depends(async_get_db)],
    current_user: Annotated[UserRead, Depends(get_current_user)]
):
    """Update an item."""
    db_item = await crud_items.get(db=db, id=item_id)
    if not db_item:
        raise HTTPException(status_code=404, detail="Item not found")
    
    updated_item = await crud_items.update(db=db, object=item_update, id=item_id)
    return updated_item


@router.delete("/{item_id}")
async def delete_item(
    item_id: int,
    db: Annotated[AsyncSession, Depends(async_get_db)],
    current_user: Annotated[UserRead, Depends(get_current_user)]
):
    """Delete an item."""
    db_item = await crud_items.get(db=db, id=item_id)
    if not db_item:
        raise HTTPException(status_code=404, detail="Item not found")
    
    await crud_items.delete(db=db, id=item_id)
    return {"message": "Item deleted successfully"}
```

### 5. Register the Router

Add your new router to `src/app/api/v1/__init__.py`:

```python
from fastapi import APIRouter

from app.api.v1.login import router as login_router
from app.api.v1.logout import router as logout_router
from app.api.v1.posts import router as posts_router
from app.api.v1.rate_limits import router as rate_limits_router
from app.api.v1.tasks import router as tasks_router
from app.api.v1.tiers import router as tiers_router
from app.api.v1.users import router as users_router
from app.api.v1.items import router as items_router  # Add this line

router = APIRouter(prefix="/v1")
router.include_router(login_router, prefix="/login")
router.include_router(logout_router, prefix="/logout") 
router.include_router(users_router, prefix="/users")
router.include_router(posts_router, prefix="/posts")
router.include_router(tasks_router, prefix="/tasks")
router.include_router(tiers_router, prefix="/tiers")
router.include_router(rate_limits_router, prefix="/rate_limits")
router.include_router(items_router, prefix="/items")  # Add this line
```

### 6. Create and Run Migration

Import your new model in `src/app/models/__init__.py`:

```python
from .user import User
from .post import Post
from .tier import Tier
from .rate_limit import RateLimit
from .item import Item  # Add this line
```

Create and run the migration:

```bash
# For Docker Compose
docker compose exec web alembic revision --autogenerate -m "Add items table"
docker compose exec web alembic upgrade head

# For manual installation
cd src
uv run alembic revision --autogenerate -m "Add items table"
uv run alembic upgrade head
```

### 7. Test Your New Endpoint

Restart your application and test the new endpoints:

```bash
# Create an item
curl -X POST "http://localhost:8000/api/v1/items/" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN_HERE" \
  -d '{
    "name": "My First Item",
    "description": "This is a test item"
  }'

# Get all items
curl -X GET "http://localhost:8000/api/v1/items/" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN_HERE"
```

## Debugging Common Issues

### Logs and Monitoring

#### Check Application Logs

```bash
# For Docker Compose
docker compose logs web

# For manual installation
tail -f src/app/logs/app.log
```

#### Check Database Logs

```bash
# For Docker Compose
docker compose logs db
```

#### Check Worker Logs

```bash
# For Docker Compose
docker compose logs worker
```

### Performance Testing

#### Test API Response Times

```bash
# Test endpoint performance
curl -w "Time: %{time_total}s\n" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN_HERE" \
  http://localhost:8000/api/v1/users/me
```

#### Test Database Performance

```bash
# Check active connections
docker compose exec db psql -U postgres -d myapp -c "SELECT count(*) FROM pg_stat_activity;"
```

## Monitoring Dashboard

### Redis Monitor

```bash
# Monitor Redis operations
docker compose exec redis redis-cli monitor
```

### Database Activity

```bash
# Check database activity
docker compose exec db psql -U postgres -d myapp -c "SELECT * FROM pg_stat_activity;"
```

## Next Steps

Now that you've verified everything works and created your first custom endpoint, you're ready to dive deeper:

### Essential Learning

1. **[Project Structure](../user-guide/project-structure.md)** - Understand how the code is organized
2. **[Database Guide](../user-guide/database/index.md)** - Learn about models, schemas, and CRUD operations
3. **[Authentication](../user-guide/authentication/index.md)** - Deep dive into JWT and user management

### Advanced Features

1. **[Caching](../user-guide/caching/index.md)** - Speed up your API with Redis caching
2. **[Background Tasks](../user-guide/background-tasks/index.md)** - Process long-running tasks asynchronously
3. **[Rate Limiting](../user-guide/rate-limiting/index.md)** - Protect your API from abuse

### Development Workflow

1. **[Development Guide](../user-guide/development.md)** - Best practices for extending the boilerplate
2. **[Testing](../user-guide/testing.md)** - Write tests for your new features
3. **[Production](../user-guide/production.md)** - Deploy your API to production

## Getting Help

If you encounter any issues:

1. **Check the logs** for error messages
2. **Verify your configuration** in the `.env` file
3. **Review the [GitHub Issues](https://github.com/benavlabs/fastapi-boilerplate/issues)** for common solutions
4. **Search [existing issues](https://github.com/benavlabs/fastapi-boilerplate/issues)** on GitHub
5. **Create a [new issue](https://github.com/benavlabs/fastapi-boilerplate/issues/new)** with detailed information

## Congratulations!

You've successfully:

- Verified your FastAPI Boilerplate installation
- Tested core API functionality
- Created your first custom endpoint
- Run database migrations
- Tested authentication and CRUD operations

You're now ready to build amazing APIs with FastAPI! 