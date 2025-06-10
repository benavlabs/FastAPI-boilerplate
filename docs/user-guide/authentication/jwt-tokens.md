# JWT Tokens

JSON Web Tokens (JWT) form the backbone of modern web authentication. This comprehensive guide explains how the boilerplate implements a secure, stateless authentication system using access and refresh tokens.

## Understanding JWT Authentication

JWT tokens are self-contained, digitally signed packages of information that can be safely transmitted between parties. Unlike traditional session-based authentication that requires server-side storage, JWT tokens are stateless - all the information needed to verify a user's identity is contained within the token itself.

### Why Use JWT?

**Stateless Design**: No need to store session data on the server, making it perfect for distributed systems and microservices.

**Scalability**: Since tokens contain all necessary information, they work seamlessly across multiple servers without shared session storage.

**Security**: Digital signatures ensure tokens can't be tampered with, and expiration times limit exposure if compromised.

**Cross-Domain Support**: Unlike cookies, JWT tokens work across different domains and can be used in mobile applications.

## Token Types

The authentication system uses a **dual-token approach** for maximum security and user experience:

### Access Tokens
Access tokens are short-lived credentials that prove a user's identity for API requests. Think of them as temporary keys that grant access to protected resources.

- **Purpose**: Authenticate API requests and authorize actions
- **Lifetime**: 30 minutes (configurable) - short enough to limit damage if compromised
- **Storage**: Authorization header (`Bearer <token>`) - sent with each API request
- **Usage**: Include in every call to protected endpoints

**Why Short-Lived?** If an access token is stolen (e.g., through XSS), the damage window is limited to 30 minutes before it expires naturally.

### Refresh Tokens
Refresh tokens are longer-lived credentials used solely to generate new access tokens. They provide a balance between security and user convenience.

- **Purpose**: Generate new access tokens without requiring re-login
- **Lifetime**: 7 days (configurable) - long enough for good UX, short enough for security
- **Storage**: Secure HTTP-only cookie - inaccessible to JavaScript, preventing XSS attacks
- **Usage**: Automatically used by the browser when access tokens need refreshing

**Why HTTP-Only Cookies?** This prevents malicious JavaScript from accessing refresh tokens, providing protection against XSS attacks while allowing automatic renewal.

## Token Creation

Understanding how tokens are created helps you customize the authentication system for your specific needs.

### Creating Access Tokens

Access tokens are generated during login and token refresh operations. The process involves encoding user information with an expiration time and signing it with your secret key.

```python
from datetime import timedelta
from app.core.security import create_access_token, ACCESS_TOKEN_EXPIRE_MINUTES

# Basic access token with default expiration
access_token = await create_access_token(data={"sub": username})

# Custom expiration for special cases (e.g., admin sessions)
custom_expires = timedelta(minutes=60)
access_token = await create_access_token(
    data={"sub": username}, 
    expires_delta=custom_expires
)
```

**When to Customize Expiration:**
- **High-security environments**: Shorter expiration (15 minutes)
- **Development/testing**: Longer expiration for convenience
- **Admin operations**: Variable expiration based on sensitivity

### Creating Refresh Tokens

Refresh tokens follow the same creation pattern but with longer expiration times. They're typically created only during login.

```python
from app.core.security import create_refresh_token, REFRESH_TOKEN_EXPIRE_DAYS

# Standard refresh token
refresh_token = await create_refresh_token(data={"sub": username})

# Extended refresh token for "remember me" functionality
extended_expires = timedelta(days=30)
refresh_token = await create_refresh_token(
    data={"sub": username}, 
    expires_delta=extended_expires
)
```

### Token Structure

JWT tokens consist of three parts separated by dots: `header.payload.signature`. The payload contains the actual user information and metadata.

```python
# Access token payload structure
{
    "sub": "username",           # Subject (user identifier)
    "exp": 1234567890,          # Expiration timestamp (Unix)
    "token_type": "access",     # Distinguishes from refresh tokens
    "iat": 1234567890           # Issued at (automatic)
}

# Refresh token payload structure
{
    "sub": "username",          # Same user identifier
    "exp": 1234567890,         # Longer expiration time
    "token_type": "refresh",   # Prevents confusion/misuse
    "iat": 1234567890          # Issue timestamp
}
```

**Key Fields Explained:**
- **`sub` (Subject)**: Identifies the user - can be username, email, or user ID
- **`exp` (Expiration)**: Unix timestamp when token becomes invalid
- **`token_type`**: Custom field preventing tokens from being used incorrectly
- **`iat` (Issued At)**: Useful for token rotation and audit trails

## Token Verification

Token verification is a multi-step process that ensures both the token's authenticity and the user's current authorization status.

### Verifying Access Tokens

Every protected endpoint must verify the access token before processing the request. This involves checking the signature, expiration, and blacklist status.

```python
from app.core.security import verify_token, TokenType

# Verify access token in endpoint
token_data = await verify_token(token, TokenType.ACCESS, db)
if token_data:
    username = token_data.username_or_email
    # Token is valid, proceed with request processing
else:
    # Token is invalid, expired, or blacklisted
    raise UnauthorizedException("Invalid or expired token")
```

### Verifying Refresh Tokens

Refresh token verification follows the same process but with different validation rules and outcomes.

```python
# Verify refresh token for renewal
token_data = await verify_token(token, TokenType.REFRESH, db)
if token_data:
    # Generate new access token
    new_access_token = await create_access_token(
        data={"sub": token_data.username_or_email}
    )
    return {"access_token": new_access_token, "token_type": "bearer"}
else:
    # Refresh token invalid - user must log in again
    raise UnauthorizedException("Invalid refresh token")
```

### Token Verification Process

The verification process includes several security checks to prevent various attack vectors:

```python
async def verify_token(token: str, expected_token_type: TokenType, db: AsyncSession) -> TokenData | None:
    # 1. Check blacklist first (prevents use of logged-out tokens)
    is_blacklisted = await crud_token_blacklist.exists(db, token=token)
    if is_blacklisted:
        return None
    
    try:
        # 2. Verify signature and decode payload
        payload = jwt.decode(token, SECRET_KEY.get_secret_value(), algorithms=[ALGORITHM])
        
        # 3. Extract and validate claims
        username_or_email: str | None = payload.get("sub")
        token_type: str | None = payload.get("token_type")
        
        # 4. Ensure token type matches expectation
        if username_or_email is None or token_type != expected_token_type:
            return None
        
        # 5. Return validated data
        return TokenData(username_or_email=username_or_email)
        
    except JWTError:
        # Token is malformed, expired, or signature invalid
        return None
```

**Security Checks Explained:**

1. **Blacklist Check**: Prevents use of tokens from logged-out users
2. **Signature Verification**: Ensures token hasn't been tampered with
3. **Expiration Check**: Automatically handled by JWT library
4. **Type Validation**: Prevents refresh tokens from being used as access tokens
5. **Subject Validation**: Ensures token contains valid user identifier

## Client-Side Authentication Flow

Understanding the complete authentication flow helps frontend developers integrate properly with the API.

### Recommended Client Flow

**1. Login Process**
```javascript
// Send credentials to login endpoint
const response = await fetch('/api/v1/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: 'username=user&password=pass',
    credentials: 'include'  // Important: includes cookies
});

const { access_token, token_type } = await response.json();

// Store access token in memory (not localStorage)
sessionStorage.setItem('access_token', access_token);
```

**2. Making Authenticated Requests**
```javascript
// Include access token in Authorization header
const response = await fetch('/api/v1/protected-endpoint', {
    headers: {
        'Authorization': `Bearer ${sessionStorage.getItem('access_token')}`
    },
    credentials: 'include'
});
```

**3. Handling Token Expiration**
```javascript
// Automatic token refresh on 401 errors
async function apiCall(url, options = {}) {
    let response = await fetch(url, {
        ...options,
        headers: {
            ...options.headers,
            'Authorization': `Bearer ${sessionStorage.getItem('access_token')}`
        },
        credentials: 'include'
    });
    
    // If token expired, try to refresh
    if (response.status === 401) {
        const refreshResponse = await fetch('/api/v1/refresh', {
            method: 'POST',
            credentials: 'include'  // Sends refresh token cookie
        });
        
        if (refreshResponse.ok) {
            const { access_token } = await refreshResponse.json();
            sessionStorage.setItem('access_token', access_token);
            
            // Retry original request
            response = await fetch(url, {
                ...options,
                headers: {
                    ...options.headers,
                    'Authorization': `Bearer ${access_token}`
                },
                credentials: 'include'
            });
        } else {
            // Refresh failed - redirect to login
            window.location.href = '/login';
        }
    }
    
    return response;
}
```

**4. Logout Process**
```javascript
// Clear tokens and call logout endpoint
await fetch('/api/v1/logout', {
    method: 'POST',
    credentials: 'include'
});

sessionStorage.removeItem('access_token');
// Refresh token cookie is cleared by server
```

### Cookie Configuration

The refresh token cookie is configured for maximum security:

```python
response.set_cookie(
    key="refresh_token",
    value=refresh_token,
    httponly=True,    # Prevents JavaScript access (XSS protection)
    secure=True,      # HTTPS only in production
    samesite="Lax",   # CSRF protection with good usability
    max_age=REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60
)
```

**SameSite Options:**

- **`Lax`** (Recommended): Cookies sent on top-level navigation but not cross-site requests
- **`Strict`**: Maximum security but may break some user flows
- **`None`**: Required for cross-origin requests (must use with Secure)

## Token Blacklisting

Token blacklisting solves a fundamental problem with JWT tokens: once issued, they remain valid until expiration, even if the user logs out. Blacklisting provides immediate token revocation.

### Why Blacklisting Matters

Without blacklisting, logged-out users could continue accessing your API until their tokens naturally expire. This creates security risks, especially on shared computers or if tokens are compromised.

### Blacklisting Implementation

The system uses a database table to track invalidated tokens:

```python
# models/token_blacklist.py
class TokenBlacklist(Base):
    __tablename__ = "token_blacklist"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    token: Mapped[str] = mapped_column(unique=True, index=True)  # Full token string
    expires_at: Mapped[datetime] = mapped_column()              # When to clean up
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
```

**Design Considerations:**
- **Unique constraint**: Prevents duplicate entries
- **Index on token**: Fast lookup during verification
- **Expires_at field**: Enables automatic cleanup of old entries

### Blacklisting Tokens

The system provides functions for both single token and dual token blacklisting:

```python
from app.core.security import blacklist_token, blacklist_tokens

# Single token blacklisting (for specific scenarios)
await blacklist_token(token, db)

# Dual token blacklisting (standard logout)
await blacklist_tokens(access_token, refresh_token, db)
```

### Blacklisting Process

The blacklisting process extracts the expiration time from the token to set an appropriate cleanup schedule:

```python
async def blacklist_token(token: str, db: AsyncSession) -> None:
    # 1. Decode token to extract expiration (no verification needed)
    payload = jwt.decode(token, SECRET_KEY.get_secret_value(), algorithms=[ALGORITHM])
    exp_timestamp = payload.get("exp")
    
    if exp_timestamp is not None:
        # 2. Convert Unix timestamp to datetime
        expires_at = datetime.fromtimestamp(exp_timestamp)
        
        # 3. Store in blacklist with expiration
        await crud_token_blacklist.create(
            db, 
            object=TokenBlacklistCreate(token=token, expires_at=expires_at)
        )
```

**Cleanup Strategy**: Blacklisted tokens can be automatically removed from the database after their natural expiration time, preventing unlimited database growth.

## Login Flow Implementation

### Complete Login Endpoint

```python
@router.post("/login", response_model=Token)
async def login_for_access_token(
    response: Response,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: Annotated[AsyncSession, Depends(async_get_db)],
) -> dict[str, str]:
    # 1. Authenticate user
    user = await authenticate_user(
        username_or_email=form_data.username, 
        password=form_data.password, 
        db=db
    )
    
    if not user:
        raise HTTPException(
            status_code=401, 
            detail="Incorrect username or password"
        )
    
    # 2. Create access token
    access_token = await create_access_token(data={"sub": user["username"]})
    
    # 3. Create refresh token
    refresh_token = await create_refresh_token(data={"sub": user["username"]})
    
    # 4. Set refresh token as HTTP-only cookie
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=True,
        samesite="strict",
        max_age=REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60
    )
    
    return {"access_token": access_token, "token_type": "bearer"}
```

### Token Refresh Endpoint

```python
@router.post("/refresh", response_model=Token)
async def refresh_access_token(
    response: Response,
    db: Annotated[AsyncSession, Depends(async_get_db)],
    refresh_token: str = Cookie(None)
) -> dict[str, str]:
    if not refresh_token:
        raise HTTPException(status_code=401, detail="Refresh token missing")
    
    # 1. Verify refresh token
    token_data = await verify_token(refresh_token, TokenType.REFRESH, db)
    if not token_data:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    
    # 2. Create new access token
    new_access_token = await create_access_token(
        data={"sub": token_data.username_or_email}
    )
    
    # 3. Optionally create new refresh token (token rotation)
    new_refresh_token = await create_refresh_token(
        data={"sub": token_data.username_or_email}
    )
    
    # 4. Blacklist old refresh token
    await blacklist_token(refresh_token, db)
    
    # 5. Set new refresh token cookie
    response.set_cookie(
        key="refresh_token",
        value=new_refresh_token,
        httponly=True,
        secure=True,
        samesite="strict",
        max_age=REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60
    )
    
    return {"access_token": new_access_token, "token_type": "bearer"}
```

### Logout Implementation

```python
@router.post("/logout")
async def logout(
    response: Response,
    db: Annotated[AsyncSession, Depends(async_get_db)],
    current_user: dict = Depends(get_current_user),
    token: str = Depends(oauth2_scheme),
    refresh_token: str = Cookie(None)
) -> dict[str, str]:
    # 1. Blacklist access token
    await blacklist_token(token, db)
    
    # 2. Blacklist refresh token if present
    if refresh_token:
        await blacklist_token(refresh_token, db)
    
    # 3. Clear refresh token cookie
    response.delete_cookie(
        key="refresh_token",
        httponly=True,
        secure=True,
        samesite="strict"
    )
    
    return {"message": "Successfully logged out"}
```

## Authentication Dependencies

### get_current_user

```python
async def get_current_user(
    db: AsyncSession = Depends(async_get_db),
    token: str = Depends(oauth2_scheme)
) -> dict:
    # 1. Verify token
    token_data = await verify_token(token, TokenType.ACCESS, db)
    if not token_data:
        raise HTTPException(status_code=401, detail="Invalid token")
    
    # 2. Get user from database
    user = await crud_users.get(
        db=db, 
        username=token_data.username_or_email,
        schema_to_select=UserRead
    )
    
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    
    return user
```

### get_optional_user

```python
async def get_optional_user(
    db: AsyncSession = Depends(async_get_db),
    token: str = Depends(optional_oauth2_scheme)
) -> dict | None:
    if not token:
        return None
    
    try:
        return await get_current_user(db=db, token=token)
    except HTTPException:
        return None
```

### get_current_superuser

```python
async def get_current_superuser(
    current_user: dict = Depends(get_current_user)
) -> dict:
    if not current_user.get("is_superuser", False):
        raise HTTPException(
            status_code=403, 
            detail="Not enough permissions"
        )
    return current_user
```

## Configuration

### Environment Variables

```bash
# JWT Configuration
SECRET_KEY=your-secret-key-here
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7

# Security Headers
SECURE_COOKIES=true
CORS_ORIGINS=["http://localhost:3000", "https://yourapp.com"]
```

### Security Configuration

```python
# app/core/config.py
class Settings(BaseSettings):
    SECRET_KEY: SecretStr
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    
    # Cookie settings
    SECURE_COOKIES: bool = True
    COOKIE_DOMAIN: str | None = None
    COOKIE_SAMESITE: str = "strict"
```

## Security Best Practices

### Token Security

- **Use strong secrets**: Generate cryptographically secure SECRET_KEY
- **Rotate secrets**: Regularly change SECRET_KEY in production
- **Environment separation**: Different secrets for dev/staging/production
- **Secure transmission**: Always use HTTPS in production

### Cookie Security

- **HttpOnly flag**: Prevents JavaScript access to refresh tokens
- **Secure flag**: Ensures cookies only sent over HTTPS
- **SameSite attribute**: Prevents CSRF attacks
- **Domain restrictions**: Set cookie domain appropriately

### Implementation Security

- **Input validation**: Validate all token inputs
- **Rate limiting**: Implement login attempt limits
- **Audit logging**: Log authentication events
- **Token rotation**: Regularly refresh tokens

## Common Patterns

### API Key Authentication

For service-to-service communication:

```python
async def get_api_key_user(
    api_key: str = Header(None),
    db: AsyncSession = Depends(async_get_db)
) -> dict:
    if not api_key:
        raise HTTPException(status_code=401, detail="API key required")
    
    # Verify API key
    user = await crud_users.get(db=db, api_key=api_key)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid API key")
    
    return user
```

### Multiple Authentication Methods

```python
async def get_authenticated_user(
    db: AsyncSession = Depends(async_get_db),
    token: str = Depends(optional_oauth2_scheme),
    api_key: str = Header(None)
) -> dict:
    # Try JWT token first
    if token:
        try:
            return await get_current_user(db=db, token=token)
        except HTTPException:
            pass
    
    # Fall back to API key
    if api_key:
        return await get_api_key_user(api_key=api_key, db=db)
    
    raise HTTPException(status_code=401, detail="Authentication required")
```

## Troubleshooting

### Common Issues

**Token Expired**: Implement automatic refresh using refresh tokens
**Invalid Signature**: Check SECRET_KEY consistency across environments
**Blacklisted Token**: User logged out - redirect to login
**Missing Token**: Ensure Authorization header is properly set

### Debugging Tips

```python
# Enable debug logging
import logging
logging.getLogger("app.core.security").setLevel(logging.DEBUG)

# Test token validation
async def debug_token(token: str, db: AsyncSession):
    try:
        payload = jwt.decode(token, SECRET_KEY.get_secret_value(), algorithms=[ALGORITHM])
        print(f"Token payload: {payload}")
        
        is_blacklisted = await crud_token_blacklist.exists(db, token=token)
        print(f"Is blacklisted: {is_blacklisted}")
        
    except JWTError as e:
        print(f"JWT Error: {e}")
```

This comprehensive JWT implementation provides secure, scalable authentication for your FastAPI application. 