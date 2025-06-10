# Authentication & Security

Learn how to implement secure authentication in your FastAPI application. The boilerplate provides a complete JWT-based authentication system with user management, permissions, and security best practices.

## What You'll Learn

- **[JWT Tokens](jwt-tokens.md)** - Understand access and refresh token management
- **[User Management](user-management.md)** - Handle registration, login, and user profiles
- **[Permissions](permissions.md)** - Implement role-based access control and authorization

## Authentication Overview

The system uses JWT tokens with refresh token rotation for secure, stateless authentication:

```python
# Basic login flow
@router.post("/login", response_model=Token)
async def login_for_access_token(response: Response, form_data: OAuth2PasswordRequestForm):
    user = await authenticate_user(form_data.username, form_data.password, db)
    access_token = await create_access_token(data={"sub": user["username"]})
    refresh_token = await create_refresh_token(data={"sub": user["username"]})
    
    # Set secure HTTP-only cookie for refresh token
    response.set_cookie("refresh_token", refresh_token, httponly=True, secure=True)
    return {"access_token": access_token, "token_type": "bearer"}
```

## Key Features

### JWT Token System
- **Access tokens**: Short-lived (30 minutes), for API requests
- **Refresh tokens**: Long-lived (7 days), stored in secure cookies
- **Token blacklisting**: Secure logout implementation
- **Automatic expiration**: Built-in token lifecycle management

### User Management
- **Flexible authentication**: Username or email login
- **Secure passwords**: bcrypt hashing with salt
- **Profile management**: Complete user CRUD operations
- **Soft delete**: User deactivation without data loss

### Permission System
- **Superuser privileges**: Administrative access control
- **Resource ownership**: User-specific data access
- **User tiers**: Subscription-based feature access
- **Rate limiting**: Per-user and per-tier API limits

## Authentication Patterns

### Endpoint Protection

```python
# Required authentication
@router.get("/protected")
async def protected_endpoint(current_user: dict = Depends(get_current_user)):
    return {"message": f"Hello {current_user['username']}"}

# Optional authentication
@router.get("/public")
async def public_endpoint(user: dict | None = Depends(get_optional_user)):
    if user:
        return {"premium_content": True}
    return {"premium_content": False}

# Superuser only
@router.get("/admin", dependencies=[Depends(get_current_superuser)])
async def admin_endpoint():
    return {"admin_data": "sensitive"}
```

### Resource Ownership

```python
@router.patch("/posts/{post_id}")
async def update_post(post_id: int, current_user: dict = Depends(get_current_user)):
    post = await crud_posts.get(db=db, id=post_id)
    
    # Check ownership or admin privileges
    if post["created_by_user_id"] != current_user["id"] and not current_user["is_superuser"]:
        raise ForbiddenException("Cannot update other users' posts")
    
    return await crud_posts.update(db=db, id=post_id, object=updates)
```

## Security Features

### Token Security
- Short-lived access tokens limit exposure
- HTTP-only refresh token cookies prevent XSS
- Token blacklisting enables secure logout
- Configurable token expiration times

### Password Security
- bcrypt hashing with automatic salt generation
- Configurable password complexity requirements
- No plain text passwords stored anywhere
- Rate limiting on authentication endpoints

### API Protection
- CORS policies for cross-origin request control
- Rate limiting prevents brute force attacks
- Input validation prevents injection attacks
- Consistent error messages prevent information disclosure

## Configuration

### JWT Settings
```env
SECRET_KEY="your-super-secret-key-here"
ALGORITHM="HS256"
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7
```

### Security Settings
```env
# Cookie security
COOKIE_SECURE=true
COOKIE_SAMESITE="lax"

# Password requirements
PASSWORD_MIN_LENGTH=8
ENABLE_PASSWORD_COMPLEXITY=true
```

## Getting Started

Follow this progressive learning path:

### 1. **[JWT Tokens](jwt-tokens.md)** - Foundation
Understand how JWT tokens work, including access and refresh token management, verification, and blacklisting.

### 2. **[User Management](user-management.md)** - Core Features
Implement user registration, login, profile management, and administrative operations.

### 3. **[Permissions](permissions.md)** - Access Control
Set up role-based access control, resource ownership checking, and tier-based permissions.

## Implementation Examples

### Quick Authentication Setup

```python
# Protect an endpoint
@router.get("/my-data")
async def get_my_data(current_user: dict = Depends(get_current_user)):
    return await get_user_specific_data(current_user["id"])

# Check user permissions
def check_tier_access(user: dict, required_tier: str):
    if not user.get("tier") or user["tier"]["name"] != required_tier:
        raise ForbiddenException(f"Requires {required_tier} tier")

# Custom authentication dependency
async def get_premium_user(current_user: dict = Depends(get_current_user)):
    check_tier_access(current_user, "Pro")
    return current_user
```

### Frontend Integration

```javascript
// Basic authentication flow
class AuthManager {
    async login(username, password) {
        const response = await fetch('/api/v1/login', {
            method: 'POST',
            headers: {'Content-Type': 'application/x-www-form-urlencoded'},
            body: new URLSearchParams({username, password})
        });
        
        const tokens = await response.json();
        localStorage.setItem('access_token', tokens.access_token);
        return tokens;
    }
    
    async makeAuthenticatedRequest(url, options = {}) {
        const token = localStorage.getItem('access_token');
        return fetch(url, {
            ...options,
            headers: {
                ...options.headers,
                'Authorization': `Bearer ${token}`
            }
        });
    }
}
```

## What's Next

Start building your authentication system:

1. **[JWT Tokens](jwt-tokens.md)** - Learn token creation, verification, and lifecycle management
2. **[User Management](user-management.md)** - Implement registration, login, and profile operations  
3. **[Permissions](permissions.md)** - Add authorization patterns and access control

The authentication system provides a secure foundation for your API. Each guide includes practical examples and implementation details for production-ready authentication. 