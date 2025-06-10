# Testing Guide

This guide covers comprehensive testing strategies for the FastAPI boilerplate, including unit tests, integration tests, and API testing.

## Test Setup

### Testing Dependencies

The boilerplate uses these testing libraries:

- **pytest** - Testing framework
- **pytest-asyncio** - Async test support
- **httpx** - Async HTTP client for API tests
- **pytest-cov** - Coverage reporting
- **faker** - Test data generation

### Test Configuration

#### pytest.ini

```ini
[tool:pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
addopts = 
    -v
    --strict-markers
    --strict-config
    --cov=src
    --cov-report=term-missing
    --cov-report=html
    --cov-report=xml
    --cov-fail-under=80
markers =
    unit: Unit tests
    integration: Integration tests
    api: API tests
    slow: Slow tests
asyncio_mode = auto
```

#### Test Database Setup

Create `tests/conftest.py`:

```python
import asyncio
import pytest
import pytest_asyncio
from typing import AsyncGenerator
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from faker import Faker

from src.app.core.config import settings
from src.app.core.db.database import Base, async_get_db
from src.app.main import app
from src.app.models.user import User
from src.app.models.post import Post
from src.app.core.security import get_password_hash

# Test database configuration
TEST_DATABASE_URL = "postgresql+asyncpg://test_user:test_pass@localhost:5432/test_db"

# Create test engine and session
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestSessionLocal = sessionmaker(
    test_engine, class_=AsyncSession, expire_on_commit=False
)

fake = Faker()


@pytest_asyncio.fixture
async def async_session() -> AsyncGenerator[AsyncSession, None]:
    """Create a fresh database session for each test."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    async with TestSessionLocal() as session:
        yield session
    
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def async_client(async_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Create an async HTTP client for testing."""
    def get_test_db():
        return async_session
    
    app.dependency_overrides[async_get_db] = get_test_db
    
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client
    
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def test_user(async_session: AsyncSession) -> User:
    """Create a test user."""
    user = User(
        name=fake.name(),
        username=fake.user_name(),
        email=fake.email(),
        hashed_password=get_password_hash("testpassword123"),
        is_superuser=False
    )
    async_session.add(user)
    await async_session.commit()
    await async_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def test_superuser(async_session: AsyncSession) -> User:
    """Create a test superuser."""
    user = User(
        name="Super Admin",
        username="superadmin",
        email="admin@test.com",
        hashed_password=get_password_hash("superpassword123"),
        is_superuser=True
    )
    async_session.add(user)
    await async_session.commit()
    await async_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def test_post(async_session: AsyncSession, test_user: User) -> Post:
    """Create a test post."""
    post = Post(
        title=fake.sentence(),
        content=fake.text(),
        created_by_user_id=test_user.id
    )
    async_session.add(post)
    await async_session.commit()
    await async_session.refresh(post)
    return post


@pytest_asyncio.fixture
async def auth_headers(async_client: AsyncClient, test_user: User) -> dict:
    """Get authentication headers for a test user."""
    login_data = {
        "username": test_user.username,
        "password": "testpassword123"
    }
    
    response = await async_client.post("/api/v1/auth/login", data=login_data)
    token = response.json()["access_token"]
    
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def superuser_headers(async_client: AsyncClient, test_superuser: User) -> dict:
    """Get authentication headers for a test superuser."""
    login_data = {
        "username": test_superuser.username,
        "password": "superpassword123"
    }
    
    response = await async_client.post("/api/v1/auth/login", data=login_data)
    token = response.json()["access_token"]
    
    return {"Authorization": f"Bearer {token}"}
```

## Unit Tests

### Model Tests

```python
# tests/test_models.py
import pytest
from datetime import datetime
from src.app.models.user import User
from src.app.models.post import Post


@pytest.mark.unit
class TestUserModel:
    """Test User model functionality."""
    
    async def test_user_creation(self, async_session):
        """Test creating a user."""
        user = User(
            name="Test User",
            username="testuser",
            email="test@example.com",
            hashed_password="hashed_password"
        )
        
        async_session.add(user)
        await async_session.commit()
        await async_session.refresh(user)
        
        assert user.id is not None
        assert user.name == "Test User"
        assert user.username == "testuser"
        assert user.email == "test@example.com"
        assert user.created_at is not None
        assert user.is_superuser is False
        assert user.is_deleted is False
    
    async def test_user_relationships(self, async_session, test_user):
        """Test user relationships."""
        post = Post(
            title="Test Post",
            content="Test content",
            created_by_user_id=test_user.id
        )
        
        async_session.add(post)
        await async_session.commit()
        
        # Test relationship
        await async_session.refresh(test_user)
        assert len(test_user.posts) == 1
        assert test_user.posts[0].title == "Test Post"


@pytest.mark.unit
class TestPostModel:
    """Test Post model functionality."""
    
    async def test_post_creation(self, async_session, test_user):
        """Test creating a post."""
        post = Post(
            title="Test Post",
            content="This is test content",
            created_by_user_id=test_user.id
        )
        
        async_session.add(post)
        await async_session.commit()
        await async_session.refresh(post)
        
        assert post.id is not None
        assert post.title == "Test Post"
        assert post.content == "This is test content"
        assert post.created_by_user_id == test_user.id
        assert post.created_at is not None
        assert post.is_deleted is False
```

### Schema Tests

```python
# tests/test_schemas.py
import pytest
from pydantic import ValidationError
from src.app.schemas.user import UserCreate, UserRead, UserUpdate
from src.app.schemas.post import PostCreate, PostRead, PostUpdate


@pytest.mark.unit
class TestUserSchemas:
    """Test User schema validation."""
    
    def test_user_create_valid(self):
        """Test valid user creation schema."""
        user_data = {
            "name": "John Doe",
            "username": "johndoe",
            "email": "john@example.com",
            "password": "SecurePass123!"
        }
        
        user = UserCreate(**user_data)
        assert user.name == "John Doe"
        assert user.username == "johndoe"
        assert user.email == "john@example.com"
        assert user.password == "SecurePass123!"
    
    def test_user_create_invalid_email(self):
        """Test invalid email validation."""
        with pytest.raises(ValidationError) as exc_info:
            UserCreate(
                name="John Doe",
                username="johndoe",
                email="invalid-email",
                password="SecurePass123!"
            )
        
        errors = exc_info.value.errors()
        assert any(error['type'] == 'value_error' for error in errors)
    
    def test_user_create_short_password(self):
        """Test password length validation."""
        with pytest.raises(ValidationError) as exc_info:
            UserCreate(
                name="John Doe",
                username="johndoe",
                email="john@example.com",
                password="123"
            )
        
        errors = exc_info.value.errors()
        assert any(error['type'] == 'value_error' for error in errors)
    
    def test_user_update_partial(self):
        """Test partial user update."""
        update_data = {"name": "Jane Doe"}
        user_update = UserUpdate(**update_data)
        
        assert user_update.name == "Jane Doe"
        assert user_update.username is None
        assert user_update.email is None


@pytest.mark.unit
class TestPostSchemas:
    """Test Post schema validation."""
    
    def test_post_create_valid(self):
        """Test valid post creation."""
        post_data = {
            "title": "Test Post",
            "content": "This is a test post content"
        }
        
        post = PostCreate(**post_data)
        assert post.title == "Test Post"
        assert post.content == "This is a test post content"
    
    def test_post_create_empty_title(self):
        """Test empty title validation."""
        with pytest.raises(ValidationError):
            PostCreate(
                title="",
                content="This is a test post content"
            )
    
    def test_post_create_long_title(self):
        """Test title length validation."""
        with pytest.raises(ValidationError):
            PostCreate(
                title="x" * 101,  # Exceeds max length
                content="This is a test post content"
            )
```

### CRUD Tests

```python
# tests/test_crud.py
import pytest
from src.app.crud.crud_users import crud_users
from src.app.crud.crud_posts import crud_posts
from src.app.schemas.user import UserCreate, UserUpdate
from src.app.schemas.post import PostCreate, PostUpdate


@pytest.mark.unit
class TestUserCRUD:
    """Test User CRUD operations."""
    
    async def test_create_user(self, async_session):
        """Test creating a user."""
        user_data = UserCreate(
            name="CRUD User",
            username="cruduser",
            email="crud@example.com",
            password="password123"
        )
        
        user = await crud_users.create(db=async_session, object=user_data)
        assert user["name"] == "CRUD User"
        assert user["username"] == "cruduser"
        assert user["email"] == "crud@example.com"
        assert "id" in user
    
    async def test_get_user(self, async_session, test_user):
        """Test getting a user."""
        retrieved_user = await crud_users.get(
            db=async_session, 
            id=test_user.id
        )
        
        assert retrieved_user is not None
        assert retrieved_user["id"] == test_user.id
        assert retrieved_user["name"] == test_user.name
        assert retrieved_user["username"] == test_user.username
    
    async def test_get_user_by_email(self, async_session, test_user):
        """Test getting a user by email."""
        retrieved_user = await crud_users.get(
            db=async_session,
            email=test_user.email
        )
        
        assert retrieved_user is not None
        assert retrieved_user["email"] == test_user.email
    
    async def test_update_user(self, async_session, test_user):
        """Test updating a user."""
        update_data = UserUpdate(name="Updated Name")
        
        updated_user = await crud_users.update(
            db=async_session,
            object=update_data,
            id=test_user.id
        )
        
        assert updated_user["name"] == "Updated Name"
        assert updated_user["id"] == test_user.id
    
    async def test_delete_user(self, async_session, test_user):
        """Test soft deleting a user."""
        await crud_users.delete(db=async_session, id=test_user.id)
        
        # User should be soft deleted
        deleted_user = await crud_users.get(
            db=async_session,
            id=test_user.id,
            is_deleted=True
        )
        
        assert deleted_user is not None
        assert deleted_user["is_deleted"] is True
    
    async def test_get_multi_users(self, async_session):
        """Test getting multiple users."""
        # Create multiple users
        for i in range(5):
            user_data = UserCreate(
                name=f"User {i}",
                username=f"user{i}",
                email=f"user{i}@example.com",
                password="password123"
            )
            await crud_users.create(db=async_session, object=user_data)
        
        # Get users with pagination
        result = await crud_users.get_multi(
            db=async_session,
            offset=0,
            limit=3
        )
        
        assert len(result["data"]) == 3
        assert result["total_count"] == 5
        assert result["has_more"] is True


@pytest.mark.unit
class TestPostCRUD:
    """Test Post CRUD operations."""
    
    async def test_create_post(self, async_session, test_user):
        """Test creating a post."""
        post_data = PostCreate(
            title="Test Post",
            content="This is test content"
        )
        
        post = await crud_posts.create(
            db=async_session,
            object=post_data,
            created_by_user_id=test_user.id
        )
        
        assert post["title"] == "Test Post"
        assert post["content"] == "This is test content"
        assert post["created_by_user_id"] == test_user.id
    
    async def test_get_posts_by_user(self, async_session, test_user):
        """Test getting posts by user."""
        # Create multiple posts
        for i in range(3):
            post_data = PostCreate(
                title=f"Post {i}",
                content=f"Content {i}"
            )
            await crud_posts.create(
                db=async_session,
                object=post_data,
                created_by_user_id=test_user.id
            )
        
        # Get posts by user
        result = await crud_posts.get_multi(
            db=async_session,
            created_by_user_id=test_user.id
        )
        
        assert len(result["data"]) == 3
        assert result["total_count"] == 3
```

## Integration Tests

### API Endpoint Tests

```python
# tests/test_api_users.py
import pytest
from httpx import AsyncClient


@pytest.mark.integration
class TestUserAPI:
    """Test User API endpoints."""
    
    async def test_create_user(self, async_client: AsyncClient):
        """Test user creation endpoint."""
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
        assert data["email"] == "new@example.com"
        assert "hashed_password" not in data
        assert "id" in data
    
    async def test_create_user_duplicate_email(self, async_client: AsyncClient, test_user):
        """Test creating user with duplicate email."""
        user_data = {
            "name": "Duplicate User",
            "username": "duplicateuser",
            "email": test_user.email,  # Use existing email
            "password": "SecurePass123!"
        }
        
        response = await async_client.post("/api/v1/users", json=user_data)
        assert response.status_code == 409  # Conflict
    
    async def test_get_users(self, async_client: AsyncClient):
        """Test getting users list."""
        response = await async_client.get("/api/v1/users")
        assert response.status_code == 200
        
        data = response.json()
        assert "data" in data
        assert "total_count" in data
        assert "has_more" in data
        assert isinstance(data["data"], list)
    
    async def test_get_user_by_id(self, async_client: AsyncClient, test_user):
        """Test getting specific user."""
        response = await async_client.get(f"/api/v1/users/{test_user.id}")
        assert response.status_code == 200
        
        data = response.json()
        assert data["id"] == test_user.id
        assert data["name"] == test_user.name
        assert data["username"] == test_user.username
    
    async def test_get_user_not_found(self, async_client: AsyncClient):
        """Test getting non-existent user."""
        response = await async_client.get("/api/v1/users/99999")
        assert response.status_code == 404
    
    async def test_update_user_authorized(self, async_client: AsyncClient, test_user, auth_headers):
        """Test updating user with proper authorization."""
        update_data = {"name": "Updated Name"}
        
        response = await async_client.patch(
            f"/api/v1/users/{test_user.id}",
            json=update_data,
            headers=auth_headers
        )
        assert response.status_code == 200
        
        data = response.json()
        assert data["name"] == "Updated Name"
        assert data["id"] == test_user.id
    
    async def test_update_user_unauthorized(self, async_client: AsyncClient, test_user):
        """Test updating user without authorization."""
        update_data = {"name": "Updated Name"}
        
        response = await async_client.patch(
            f"/api/v1/users/{test_user.id}",
            json=update_data
        )
        assert response.status_code == 401
    
    async def test_delete_user_superuser(self, async_client: AsyncClient, test_user, superuser_headers):
        """Test deleting user as superuser."""
        response = await async_client.delete(
            f"/api/v1/users/{test_user.id}",
            headers=superuser_headers
        )
        assert response.status_code == 200
    
    async def test_delete_user_forbidden(self, async_client: AsyncClient, test_user, auth_headers):
        """Test deleting user without superuser privileges."""
        response = await async_client.delete(
            f"/api/v1/users/{test_user.id}",
            headers=auth_headers
        )
        assert response.status_code == 403


@pytest.mark.integration
class TestAuthAPI:
    """Test Authentication API endpoints."""
    
    async def test_login_success(self, async_client: AsyncClient, test_user):
        """Test successful login."""
        login_data = {
            "username": test_user.username,
            "password": "testpassword123"
        }
        
        response = await async_client.post("/api/v1/auth/login", data=login_data)
        assert response.status_code == 200
        
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"
    
    async def test_login_invalid_credentials(self, async_client: AsyncClient, test_user):
        """Test login with invalid credentials."""
        login_data = {
            "username": test_user.username,
            "password": "wrongpassword"
        }
        
        response = await async_client.post("/api/v1/auth/login", data=login_data)
        assert response.status_code == 401
    
    async def test_get_current_user(self, async_client: AsyncClient, test_user, auth_headers):
        """Test getting current user information."""
        response = await async_client.get("/api/v1/auth/me", headers=auth_headers)
        assert response.status_code == 200
        
        data = response.json()
        assert data["id"] == test_user.id
        assert data["username"] == test_user.username
    
    async def test_refresh_token(self, async_client: AsyncClient, test_user):
        """Test token refresh."""
        # First login to get refresh token
        login_data = {
            "username": test_user.username,
            "password": "testpassword123"
        }
        
        login_response = await async_client.post("/api/v1/auth/login", data=login_data)
        refresh_token = login_response.json()["refresh_token"]
        
        # Use refresh token to get new access token
        refresh_response = await async_client.post(
            "/api/v1/auth/refresh",
            headers={"Authorization": f"Bearer {refresh_token}"}
        )
        
        assert refresh_response.status_code == 200
        data = refresh_response.json()
        assert "access_token" in data
```

## Running Tests

### Basic Test Commands

```bash
# Run all tests
uv run pytest

# Run specific test categories
uv run pytest -m unit
uv run pytest -m integration
uv run pytest -m api

# Run tests with coverage
uv run pytest --cov=src --cov-report=html

# Run tests in parallel
uv run pytest -n auto

# Run specific test file
uv run pytest tests/test_api_users.py

# Run with verbose output
uv run pytest -v

# Run tests matching pattern
uv run pytest -k "test_user"

# Run tests and stop on first failure
uv run pytest -x

# Run slow tests
uv run pytest -m slow
```

### Test Environment Setup

```bash
# Set up test database
createdb test_db

# Run tests with specific environment
ENVIRONMENT=testing uv run pytest

# Run tests with debug output
uv run pytest -s --log-cli-level=DEBUG
```

## Testing Best Practices

### Test Organization

- **Separate concerns**: Unit tests for business logic, integration tests for API endpoints
- **Use fixtures**: Create reusable test data and setup
- **Test isolation**: Each test should be independent
- **Clear naming**: Test names should describe what they're testing

### Test Data

- **Use factories**: Create test data programmatically
- **Avoid hardcoded values**: Use variables and constants
- **Clean up**: Ensure tests don't leave data behind
- **Realistic data**: Use faker or similar libraries for realistic test data

### Assertions

- **Specific assertions**: Test specific behaviors, not just "it works"
- **Multiple assertions**: Test all relevant aspects of the response
- **Error cases**: Test error conditions and edge cases
- **Performance**: Include performance tests for critical paths

### Mocking

```python
# Example of mocking external dependencies
from unittest.mock import patch, AsyncMock

@pytest.mark.unit
async def test_external_api_call():
    """Test function that calls external API."""
    with patch('src.app.services.external_api.make_request') as mock_request:
        mock_request.return_value = {"status": "success"}
        
        result = await some_function_that_calls_external_api()
        
        assert result["status"] == "success"
        mock_request.assert_called_once()
```

### Continuous Integration

```yaml
# .github/workflows/test.yml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    
    services:
      postgres:
        image: postgres:15
        env:
          POSTGRES_USER: test_user
          POSTGRES_PASSWORD: test_pass
          POSTGRES_DB: test_db
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
    
    steps:
    - uses: actions/checkout@v3
    
    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: 3.11
    
    - name: Install dependencies
      run: |
        pip install uv
        uv sync
    
    - name: Run tests
      run: uv run pytest --cov=src --cov-report=xml
    
    - name: Upload coverage
      uses: codecov/codecov-action@v3
      with:
        file: ./coverage.xml
```

This testing guide provides comprehensive coverage of testing strategies for the FastAPI boilerplate, ensuring reliable and maintainable code. 