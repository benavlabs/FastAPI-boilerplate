# API Exception Handling

Learn how to handle errors properly in your API endpoints using the boilerplate's built-in exceptions and patterns.

## Quick Start

The boilerplate provides ready-to-use exceptions that return proper HTTP status codes:

```python
from app.core.exceptions.http_exceptions import NotFoundException

@router.get("/{user_id}")
async def get_user(user_id: int, db: AsyncSession):
    user = await crud_users.get(db=db, id=user_id)
    if not user:
        raise NotFoundException("User not found")  # Returns 404
    return user
```

That's it! The exception automatically becomes a proper JSON error response.

## Built-in Exceptions

The boilerplate includes common HTTP exceptions you'll need:

### NotFoundException (404)
```python
from app.core.exceptions.http_exceptions import NotFoundException

@router.get("/{user_id}")
async def get_user(user_id: int):
    user = await crud_users.get(db=db, id=user_id)
    if not user:
        raise NotFoundException("User not found")
    return user

# Returns:
# Status: 404
# {"detail": "User not found"}
```

### DuplicateValueException (409)
```python
from app.core.exceptions.http_exceptions import DuplicateValueException

@router.post("/")
async def create_user(user_data: UserCreate):
    if await crud_users.exists(db=db, email=user_data.email):
        raise DuplicateValueException("Email already exists")
    
    return await crud_users.create(db=db, object=user_data)

# Returns:
# Status: 409
# {"detail": "Email already exists"}
```

### ForbiddenException (403)
```python
from app.core.exceptions.http_exceptions import ForbiddenException

@router.delete("/{user_id}")
async def delete_user(
    user_id: int,
    current_user: Annotated[dict, Depends(get_current_user)]
):
    if current_user["id"] != user_id and not current_user["is_superuser"]:
        raise ForbiddenException("You can only delete your own account")
    
    await crud_users.delete(db=db, id=user_id)
    return {"message": "User deleted"}

# Returns:
# Status: 403
# {"detail": "You can only delete your own account"}
```

### UnauthorizedException (401)
```python
from app.core.exceptions.http_exceptions import UnauthorizedException

# This is typically used in the auth system, but you can use it too:
@router.get("/admin-only")
async def admin_endpoint():
    # Some validation logic
    if not user_is_admin:
        raise UnauthorizedException("Admin access required")
    
    return {"data": "secret admin data"}

# Returns:
# Status: 401
# {"detail": "Admin access required"}
```

## Common Patterns

### Check Before Create
```python
@router.post("/", response_model=UserRead)
async def create_user(user_data: UserCreate, db: AsyncSession):
    # Check email
    if await crud_users.exists(db=db, email=user_data.email):
        raise DuplicateValueException("Email already exists")
    
    # Check username  
    if await crud_users.exists(db=db, username=user_data.username):
        raise DuplicateValueException("Username already taken")
    
    # Create user
    return await crud_users.create(db=db, object=user_data)

# For public registration endpoints, consider rate limiting
# to prevent email enumeration attacks
```

### Check Before Update
```python
@router.patch("/{user_id}", response_model=UserRead)
async def update_user(
    user_id: int,
    user_data: UserUpdate,
    db: AsyncSession
):
    # Check if user exists
    if not await crud_users.exists(db=db, id=user_id):
        raise NotFoundException("User not found")
    
    # Check for email conflicts (if email is being updated)
    if user_data.email:
        existing = await crud_users.get(db=db, email=user_data.email)
        if existing and existing.id != user_id:
            raise DuplicateValueException("Email already taken")
    
    # Update user
    return await crud_users.update(db=db, object=user_data, id=user_id)
```

### Check Ownership
```python
@router.get("/{post_id}")
async def get_post(
    post_id: int,
    current_user: Annotated[dict, Depends(get_current_user)],
    db: AsyncSession
):
    post = await crud_posts.get(db=db, id=post_id)
    if not post:
        raise NotFoundException("Post not found")
    
    # Check if user owns the post or is admin
    if post.author_id != current_user["id"] and not current_user["is_superuser"]:
        raise ForbiddenException("You can only view your own posts")
    
    return post
```

## Validation Errors

FastAPI automatically handles Pydantic validation errors, but you can catch and customize them:

```python
from fastapi import HTTPException
from pydantic import ValidationError

@router.post("/")
async def create_user(user_data: UserCreate):
    try:
        # If user_data fails validation, Pydantic raises ValidationError
        # FastAPI automatically converts this to a 422 response
        return await crud_users.create(db=db, object=user_data)
    except ValidationError as e:
        # You can catch and customize if needed
        raise HTTPException(
            status_code=400,
            detail=f"Invalid data: {e.errors()}"
        )
```

## Standard HTTP Exceptions

For other status codes, use FastAPI's HTTPException:

```python
from fastapi import HTTPException

# Bad Request (400)
@router.post("/")
async def create_something(data: dict):
    if not data.get("required_field"):
        raise HTTPException(
            status_code=400,
            detail="required_field is missing"
        )

# Too Many Requests (429)
@router.post("/")
async def rate_limited_endpoint():
    if rate_limit_exceeded():
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded. Try again later."
        )

# Internal Server Error (500)
@router.get("/")
async def risky_endpoint():
    try:
        # Some operation that might fail
        result = risky_operation()
        return result
    except Exception as e:
        # Log the error
        logger.error(f"Unexpected error: {e}")
        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred"
        )
```

## Creating Custom Exceptions

If you need custom exceptions, follow the boilerplate's pattern:

```python
# In app/core/exceptions/http_exceptions.py (add to existing file)
from fastapi import HTTPException

class PaymentRequiredException(HTTPException):
    """402 Payment Required"""
    def __init__(self, detail: str = "Payment required"):
        super().__init__(status_code=402, detail=detail)

class TooManyRequestsException(HTTPException):
    """429 Too Many Requests"""
    def __init__(self, detail: str = "Too many requests"):
        super().__init__(status_code=429, detail=detail)

# Use them in your endpoints
from app.core.exceptions.http_exceptions import PaymentRequiredException

@router.get("/premium-feature")
async def premium_feature(current_user: dict):
    if current_user["tier"] == "free":
        raise PaymentRequiredException("Upgrade to access this feature")
    
    return {"data": "premium content"}
```

## Error Response Format

All exceptions return consistent JSON responses:

```json
{
    "detail": "Error message here"
}
```

For validation errors (422), you get more detail:

```json
{
    "detail": [
        {
            "type": "missing",
            "loc": ["body", "email"],
            "msg": "Field required",
            "input": null
        }
    ]
}
```

## Global Exception Handling

The boilerplate includes global exception handlers. You can add your own in `main.py`:

```python
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

app = FastAPI()

@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    """Handle ValueError exceptions globally"""
    return JSONResponse(
        status_code=400,
        content={"detail": f"Invalid value: {str(exc)}"}
    )

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Catch-all exception handler"""
    # Log the error
    logger.error(f"Unhandled exception: {exc}")
    
    return JSONResponse(
        status_code=500,
        content={"detail": "An unexpected error occurred"}
    )
```

## Security Considerations

### Authentication Endpoints - Use Generic Messages

For security, authentication endpoints should use generic error messages to prevent information disclosure:

```python
# SECURITY: Don't reveal if username exists
@router.post("/login")
async def login(credentials: LoginCredentials):
    user = await crud_users.get(db=db, username=credentials.username)
    
    # Don't do this - reveals if username exists
    # if not user:
    #     raise NotFoundException("User not found")
    # if not verify_password(credentials.password, user.hashed_password):
    #     raise UnauthorizedException("Invalid password")
    
    # Do this - generic message for all auth failures
    if not user or not verify_password(credentials.password, user.hashed_password):
        raise UnauthorizedException("Invalid username or password")
    
    return create_access_token(user.id)

# SECURITY: Don't reveal if email is registered during password reset
@router.post("/forgot-password")
async def forgot_password(email: str):
    user = await crud_users.get(db=db, email=email)
    
    # Don't do this - reveals if email exists
    # if not user:
    #     raise NotFoundException("Email not found")
    
    # Do this - always return success message
    if user:
        await send_password_reset_email(user.email)
    
    # Always return the same message
    return {"message": "If the email exists, a reset link has been sent"}
```

### Resource Access - Be Specific When Safe

For non-auth operations, specific messages help developers:

```python
# Safe to be specific for resource operations
@router.get("/{post_id}")
async def get_post(
    post_id: int,
    current_user: Annotated[dict, Depends(get_current_user)]
):
    post = await crud_posts.get(db=db, id=post_id)
    if not post:
        raise NotFoundException("Post not found")  # Safe to be specific
    
    if post.author_id != current_user["id"]:
        # Don't reveal post exists if user can't access it
        raise NotFoundException("Post not found")  # Generic, not "Access denied"
    
    return post
```

## Best Practices

### 1. Use Specific Exceptions (When Safe)
```python
# Good for non-sensitive operations
if not user:
    raise NotFoundException("User not found")

# Good for validation errors
raise DuplicateValueException("Username already taken")
```

### 2. Use Generic Messages for Security
```python
# Good for authentication
raise UnauthorizedException("Invalid username or password")

# Good for authorization (don't reveal resource exists)
raise NotFoundException("Resource not found")  # Instead of "Access denied"
```

### 3. Check Permissions Early
```python
@router.delete("/{user_id}")
async def delete_user(
    user_id: int,
    current_user: Annotated[dict, Depends(get_current_user)]
):
    # Check permission first
    if current_user["id"] != user_id:
        raise ForbiddenException("Cannot delete other users")
    
    # Then check if user exists
    if not await crud_users.exists(db=db, id=user_id):
        raise NotFoundException("User not found")
    
    await crud_users.delete(db=db, id=user_id)
```

### 4. Log Important Errors
```python
import logging

logger = logging.getLogger(__name__)

@router.post("/")
async def create_user(user_data: UserCreate):
    try:
        return await crud_users.create(db=db, object=user_data)
    except Exception as e:
        logger.error(f"Failed to create user: {e}")
        raise HTTPException(status_code=500, detail="User creation failed")
```

## Testing Exceptions

Test that your endpoints raise the right exceptions:

```python
import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_user_not_found(client: AsyncClient):
    response = await client.get("/api/v1/users/99999")
    assert response.status_code == 404
    assert "User not found" in response.json()["detail"]

@pytest.mark.asyncio
async def test_duplicate_email(client: AsyncClient):
    # Create a user
    await client.post("/api/v1/users/", json={
        "name": "Test User",
        "username": "test1",
        "email": "test@example.com",
        "password": "Password123!"
    })
    
    # Try to create another with same email
    response = await client.post("/api/v1/users/", json={
        "name": "Test User 2",
        "username": "test2", 
        "email": "test@example.com",  # Same email
        "password": "Password123!"
    })
    
    assert response.status_code == 409
    assert "Email already exists" in response.json()["detail"]
```

## What's Next

Now that you understand error handling:
- **[Versioning](versioning.md)** - Learn how to version your APIs
- **[Database CRUD](../database/crud.md)** - Understand the database operations
- **[Authentication](../authentication/index.md)** - Add user authentication to your APIs

Proper error handling makes your API much more user-friendly and easier to debug! 