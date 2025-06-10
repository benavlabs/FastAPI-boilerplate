# User Management

User management forms the core of any authentication system, handling everything from user registration and login to profile updates and account deletion. This section covers the complete user lifecycle with secure authentication flows and administrative operations.

## Understanding User Lifecycle

The user lifecycle in the boilerplate follows a secure, well-defined process that protects user data while providing a smooth experience. Understanding this flow helps you customize the system for your specific needs.

**Registration → Authentication → Profile Management → Administrative Operations**

Each stage has specific security considerations and business logic that ensure data integrity and user safety.

## User Registration

User registration is the entry point to your application. The process must be secure, user-friendly, and prevent common issues like duplicate accounts or weak passwords.

### Registration Process

The registration endpoint performs several validation steps before creating a user account. This multi-step validation prevents common registration issues and ensures data quality.

```python
# User registration endpoint
@router.post("/user", response_model=UserRead, status_code=201)
async def write_user(
    user: UserCreate, 
    db: AsyncSession
) -> UserRead:
    # 1. Check if email exists
    email_row = await crud_users.exists(db=db, email=user.email)
    if email_row:
        raise DuplicateValueException("Email is already registered")
    
    # 2. Check if username exists
    username_row = await crud_users.exists(db=db, username=user.username)
    if username_row:
        raise DuplicateValueException("Username not available")
    
    # 3. Hash password
    user_internal_dict = user.model_dump()
    user_internal_dict["hashed_password"] = get_password_hash(
        password=user_internal_dict["password"]
    )
    del user_internal_dict["password"]
    
    # 4. Create user
    user_internal = UserCreateInternal(**user_internal_dict)
    created_user = await crud_users.create(db=db, object=user_internal)
    
    return created_user
```

**Security Steps Explained:**

1. **Email Uniqueness**: Prevents multiple accounts with the same email, which could cause confusion and security issues
2. **Username Uniqueness**: Ensures usernames are unique identifiers within your system
3. **Password Hashing**: Converts plain text passwords into secure hashes before database storage
4. **Data Separation**: Plain text passwords are immediately removed from memory after hashing

### Registration Schema

The registration schema defines what data is required and how it's validated. This ensures consistent data quality and prevents malformed user accounts.

```python
# User registration input
class UserCreate(UserBase):
    model_config = ConfigDict(extra="forbid")
    
    password: Annotated[
        str,
        Field(
            pattern=r"^.{8,}|[0-9]+|[A-Z]+|[a-z]+|[^a-zA-Z0-9]+$",
            examples=["Str1ngst!"]
        )
    ]

# Internal schema for database storage
class UserCreateInternal(UserBase):
    hashed_password: str
```

**Schema Design Principles:**

- **`extra="forbid"`**: Rejects unexpected fields, preventing injection of unauthorized data
- **Password Patterns**: Enforces minimum security requirements for passwords
- **Separation of Concerns**: External schema accepts passwords, internal schema stores hashes

## User Authentication

Authentication verifies user identity using credentials. The process must be secure against common attacks while remaining user-friendly.

### Authentication Process

```python
async def authenticate_user(username_or_email: str, password: str, db: AsyncSession) -> dict | False:
    # 1. Get user by email or username
    if "@" in username_or_email:
        db_user = await crud_users.get(db=db, email=username_or_email, is_deleted=False)
    else:
        db_user = await crud_users.get(db=db, username=username_or_email, is_deleted=False)
    
    if not db_user:
        return False
    
    # 2. Verify password
    if not await verify_password(password, db_user["hashed_password"]):
        return False
    
    return db_user
```

**Security Considerations:**

- **Flexible Login**: Accepts both username and email for better user experience
- **Soft Delete Check**: `is_deleted=False` prevents deleted users from logging in
- **Consistent Timing**: Both user lookup and password verification take similar time

### Password Security

Password security is critical for protecting user accounts. The system uses industry-standard bcrypt hashing with automatic salt generation.

```python
import bcrypt

async def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against its hash."""
    correct_password: bool = bcrypt.checkpw(
        plain_password.encode(), 
        hashed_password.encode()
    )
    return correct_password

def get_password_hash(password: str) -> str:
    """Generate password hash with salt."""
    hashed_password: str = bcrypt.hashpw(
        password.encode(), 
        bcrypt.gensalt()
    ).decode()
    return hashed_password
```

**Why bcrypt?**

- **Adaptive Hashing**: Computationally expensive, making brute force attacks impractical
- **Automatic Salt**: Each password gets a unique salt, preventing rainbow table attacks
- **Future-Proof**: Can increase computational cost as hardware improves

### Login Validation

Client-side validation provides immediate feedback but should never be the only validation layer.

```python
# Password validation pattern
PASSWORD_PATTERN = r"^.{8,}|[0-9]+|[A-Z]+|[a-z]+|[^a-zA-Z0-9]+$"

# Frontend validation (example)
function validatePassword(password) {
    const minLength = password.length >= 8;
    const hasNumber = /[0-9]/.test(password);
    const hasUpper = /[A-Z]/.test(password);
    const hasLower = /[a-z]/.test(password);
    const hasSpecial = /[^a-zA-Z0-9]/.test(password);
    
    return minLength && hasNumber && hasUpper && hasLower && hasSpecial;
}
```

**Validation Strategy:**

- **Server-Side**: Always validate on the server - client validation can be bypassed
- **Client-Side**: Provides immediate feedback for better user experience
- **Progressive**: Validate as user types to catch issues early

## Profile Management

Profile management allows users to update their information while maintaining security and data integrity.

### Get Current User Profile

Retrieving the current user's profile is a fundamental operation that should be fast and secure.

```python
@router.get("/user/me/", response_model=UserRead)
async def read_users_me(current_user: dict = Depends(get_current_user)) -> dict:
    return current_user

# Frontend usage
async function getCurrentUser() {
    const token = localStorage.getItem('access_token');
    const response = await fetch('/api/v1/user/me/', {
        headers: {
            'Authorization': `Bearer ${token}`
        }
    });
    
    if (response.ok) {
        return await response.json();
    }
    throw new Error('Failed to get user profile');
}
```

**Design Decisions:**

- **`/me` Endpoint**: Common pattern that's intuitive for users and developers
- **Current User Dependency**: Automatically handles authentication and user lookup
- **Minimal Data**: Returns only safe, user-relevant information

### Update User Profile

Profile updates require careful validation to prevent unauthorized changes and maintain data integrity.

```python
@router.patch("/user/{username}")
async def patch_user(
    values: UserUpdate,
    username: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(async_get_db),
) -> dict[str, str]:
    # 1. Get user from database
    db_user = await crud_users.get(db=db, username=username, schema_to_select=UserRead)
    if db_user is None:
        raise NotFoundException("User not found")
    
    # 2. Check ownership (users can only update their own profile)
    if db_user["username"] != current_user["username"]:
        raise ForbiddenException("Cannot update other users")
    
    # 3. Validate unique constraints
    if values.username and values.username != db_user["username"]:
        existing_username = await crud_users.exists(db=db, username=values.username)
        if existing_username:
            raise DuplicateValueException("Username not available")
    
    if values.email and values.email != db_user["email"]:
        existing_email = await crud_users.exists(db=db, email=values.email)
        if existing_email:
            raise DuplicateValueException("Email is already registered")
    
    # 4. Update user
    await crud_users.update(db=db, object=values, username=username)
    return {"message": "User updated"}
```

**Security Measures:**

1. **Ownership Verification**: Users can only update their own profiles
2. **Uniqueness Checks**: Prevents conflicts when changing username/email
3. **Partial Updates**: Only provided fields are updated
4. **Input Validation**: Pydantic schemas validate all input data

## User Deletion

User deletion requires careful consideration of data retention, user rights, and system integrity.

### Self-Deletion

Users should be able to delete their own accounts, but the process should be secure and potentially reversible.

```python
@router.delete("/user/{username}")
async def erase_user(
    username: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(async_get_db),
    token: str = Depends(oauth2_scheme),
) -> dict[str, str]:
    # 1. Get user from database
    db_user = await crud_users.get(db=db, username=username, schema_to_select=UserRead)
    if not db_user:
        raise NotFoundException("User not found")
    
    # 2. Check ownership
    if username != current_user["username"]:
        raise ForbiddenException()
    
    # 3. Soft delete user
    await crud_users.delete(db=db, username=username)
    
    # 4. Blacklist current token
    await blacklist_token(token=token, db=db)
    
    return {"message": "User deleted"}
```

**Soft Delete Benefits:**

- **Data Recovery**: Users can be restored if needed
- **Audit Trail**: Maintain records for compliance
- **Relationship Integrity**: Related data (posts, comments) remain accessible
- **Gradual Cleanup**: Allow time for data migration or backup

### Admin Deletion (Hard Delete)

Administrators may need to permanently remove users in specific circumstances.

```python
@router.delete("/db_user/{username}", dependencies=[Depends(get_current_superuser)])
async def erase_db_user(
    username: str,
    db: AsyncSession = Depends(async_get_db),
    token: str = Depends(oauth2_scheme),
) -> dict[str, str]:
    # 1. Check if user exists
    db_user = await crud_users.exists(db=db, username=username)
    if not db_user:
        raise NotFoundException("User not found")
    
    # 2. Hard delete from database
    await crud_users.db_delete(db=db, username=username)
    
    # 3. Blacklist current token
    await blacklist_token(token=token, db=db)
    
    return {"message": "User deleted from the database"}
```

**When to Use Hard Delete:**

- **Legal Requirements**: GDPR "right to be forgotten" requests
- **Data Breach Response**: Complete removal of compromised accounts
- **Spam/Abuse**: Permanent removal of malicious accounts

## Administrative Operations

### List All Users

```python
@router.get("/users", response_model=PaginatedListResponse[UserRead])
async def read_users(
    db: AsyncSession = Depends(async_get_db), 
    page: int = 1, 
    items_per_page: int = 10
) -> dict:
    users_data = await crud_users.get_multi(
        db=db,
        offset=compute_offset(page, items_per_page),
        limit=items_per_page,
        is_deleted=False,
    )
    
    response: dict[str, Any] = paginated_response(
        crud_data=users_data, 
        page=page, 
        items_per_page=items_per_page
    )
    return response
```

### Get User by Username

```python
@router.get("/user/{username}", response_model=UserRead)
async def read_user(
    username: str, 
    db: AsyncSession = Depends(async_get_db)
) -> UserRead:
    db_user = await crud_users.get(
        db=db, 
        username=username, 
        is_deleted=False, 
        schema_to_select=UserRead
    )
    if db_user is None:
        raise NotFoundException("User not found")
    
    return db_user
```

### User with Tier Information

```python
@router.get("/user/{username}/tier")
async def read_user_tier(
    username: str, 
    db: AsyncSession = Depends(async_get_db)
) -> dict | None:
    # 1. Get user
    db_user = await crud_users.get(db=db, username=username, schema_to_select=UserRead)
    if db_user is None:
        raise NotFoundException("User not found")
    
    # 2. Return None if no tier assigned
    if db_user["tier_id"] is None:
        return None
    
    # 3. Get tier information
    db_tier = await crud_tiers.get(db=db, id=db_user["tier_id"], schema_to_select=TierRead)
    if not db_tier:
        raise NotFoundException("Tier not found")
    
    # 4. Combine user and tier data
    user_dict = dict(db_user)  # Convert to dict if needed
    tier_dict = dict(db_tier)  # Convert to dict if needed
    
    for key, value in tier_dict.items():
        user_dict[f"tier_{key}"] = value
    
    return user_dict
```

## User Tiers and Permissions

### Assign User Tier

```python
@router.patch("/user/{username}/tier", dependencies=[Depends(get_current_superuser)])
async def patch_user_tier(
    username: str, 
    values: UserTierUpdate, 
    db: AsyncSession = Depends(async_get_db)
) -> dict[str, str]:
    # 1. Verify user exists
    db_user = await crud_users.get(db=db, username=username, schema_to_select=UserRead)
    if db_user is None:
        raise NotFoundException("User not found")
    
    # 2. Verify tier exists
    tier_exists = await crud_tiers.exists(db=db, id=values.tier_id)
    if not tier_exists:
        raise NotFoundException("Tier not found")
    
    # 3. Update user tier
    await crud_users.update(db=db, object=values, username=username)
    return {"message": "User tier updated"}

# Tier update schema
class UserTierUpdate(BaseModel):
    tier_id: int
```

### User Rate Limits

```python
@router.get("/user/{username}/rate_limits", dependencies=[Depends(get_current_superuser)])
async def read_user_rate_limits(
    username: str, 
    db: AsyncSession = Depends(async_get_db)
) -> dict[str, Any]:
    # 1. Get user
    db_user = await crud_users.get(db=db, username=username, schema_to_select=UserRead)
    if db_user is None:
        raise NotFoundException("User not found")
    
    user_dict = dict(db_user)  # Convert to dict if needed
    
    # 2. No tier assigned
    if db_user["tier_id"] is None:
        user_dict["tier_rate_limits"] = []
        return user_dict
    
    # 3. Get tier and rate limits
    db_tier = await crud_tiers.get(db=db, id=db_user["tier_id"], schema_to_select=TierRead)
    if db_tier is None:
        raise NotFoundException("Tier not found")
    
    db_rate_limits = await crud_rate_limits.get_multi(db=db, tier_id=db_tier["id"])
    user_dict["tier_rate_limits"] = db_rate_limits["data"]
    
    return user_dict
```

## User Model Structure

### Database Model

```python
class User(Base):
    __tablename__ = "user"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(30))
    username: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    hashed_password: Mapped[str]
    profile_image_url: Mapped[str] = mapped_column(default="https://www.profileimageurl.com")
    is_superuser: Mapped[bool] = mapped_column(default=False)
    tier_id: Mapped[int | None] = mapped_column(ForeignKey("tier.id"), default=None)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    updated_at: Mapped[datetime | None] = mapped_column(default=None)
    
    # Soft delete
    is_deleted: Mapped[bool] = mapped_column(default=False)
    deleted_at: Mapped[datetime | None] = mapped_column(default=None)
    
    # Relationships
    tier: Mapped["Tier"] = relationship(back_populates="users")
    posts: Mapped[list["Post"]] = relationship(back_populates="created_by_user")
```

### User Schemas

```python
# Base schema with common fields
class UserBase(BaseModel):
    name: Annotated[str, Field(min_length=2, max_length=30)]
    username: Annotated[str, Field(min_length=2, max_length=20, pattern=r"^[a-z0-9]+$")]
    email: Annotated[EmailStr, Field(examples=["user@example.com"])]

# Reading user data (API responses)
class UserRead(BaseModel):
    id: int
    name: str
    username: str
    email: str
    profile_image_url: str
    tier_id: int | None

# Full user data (internal use)
class User(TimestampSchema, UserBase, UUIDSchema, PersistentDeletion):
    profile_image_url: str = "https://www.profileimageurl.com"
    hashed_password: str
    is_superuser: bool = False
    tier_id: int | None = None
```

## Common User Operations

### Check User Existence

```python
# By email
email_exists = await crud_users.exists(db=db, email="user@example.com")

# By username
username_exists = await crud_users.exists(db=db, username="johndoe")

# By ID
user_exists = await crud_users.exists(db=db, id=123)
```

### Search Users

```python
# Get active users only
active_users = await crud_users.get_multi(
    db=db, 
    is_deleted=False,
    limit=10
)

# Get users by tier
tier_users = await crud_users.get_multi(
    db=db,
    tier_id=1,
    is_deleted=False
)

# Get superusers
superusers = await crud_users.get_multi(
    db=db,
    is_superuser=True,
    is_deleted=False
)
```

### User Statistics

```python
async def get_user_stats(db: AsyncSession) -> dict:
    # Total users
    total_users = await crud_users.count(db=db, is_deleted=False)
    
    # Active users (logged in recently)
    # This would require tracking last_login_at
    
    # Users by tier
    tier_stats = {}
    tiers = await crud_tiers.get_multi(db=db)
    for tier in tiers["data"]:
        count = await crud_users.count(db=db, tier_id=tier["id"], is_deleted=False)
        tier_stats[tier["name"]] = count
    
    return {
        "total_users": total_users,
        "tier_distribution": tier_stats
    }
```

## Frontend Integration

### Complete User Management Component

```javascript
class UserManager {
    constructor(baseUrl = '/api/v1') {
        this.baseUrl = baseUrl;
        this.token = localStorage.getItem('access_token');
    }
    
    async register(userData) {
        const response = await fetch(`${this.baseUrl}/user`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(userData)
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail);
        }
        
        return await response.json();
    }
    
    async login(username, password) {
        const response = await fetch(`${this.baseUrl}/login`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded',
            },
            body: new URLSearchParams({
                username: username,
                password: password
            })
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail);
        }
        
        const tokens = await response.json();
        localStorage.setItem('access_token', tokens.access_token);
        this.token = tokens.access_token;
        
        return tokens;
    }
    
    async getProfile() {
        const response = await fetch(`${this.baseUrl}/user/me/`, {
            headers: {
                'Authorization': `Bearer ${this.token}`
            }
        });
        
        if (!response.ok) {
            throw new Error('Failed to get profile');
        }
        
        return await response.json();
    }
    
    async updateProfile(username, updates) {
        const response = await fetch(`${this.baseUrl}/user/${username}`, {
            method: 'PATCH',
            headers: {
                'Authorization': `Bearer ${this.token}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(updates)
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail);
        }
        
        return await response.json();
    }
    
    async deleteAccount(username) {
        const response = await fetch(`${this.baseUrl}/user/${username}`, {
            method: 'DELETE',
            headers: {
                'Authorization': `Bearer ${this.token}`
            }
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail);
        }
        
        // Clear local storage
        localStorage.removeItem('access_token');
        this.token = null;
        
        return await response.json();
    }
    
    async logout() {
        const response = await fetch(`${this.baseUrl}/logout`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${this.token}`
            }
        });
        
        // Clear local storage regardless of response
        localStorage.removeItem('access_token');
        this.token = null;
        
        if (response.ok) {
            return await response.json();
        }
    }
}

// Usage
const userManager = new UserManager();

// Register new user
try {
    const user = await userManager.register({
        name: "John Doe",
        username: "johndoe",
        email: "john@example.com",
        password: "SecurePass123!"
    });
    console.log('User registered:', user);
} catch (error) {
    console.error('Registration failed:', error.message);
}

// Login
try {
    const tokens = await userManager.login('johndoe', 'SecurePass123!');
    console.log('Login successful');
    
    // Get profile
    const profile = await userManager.getProfile();
    console.log('User profile:', profile);
} catch (error) {
    console.error('Login failed:', error.message);
}
```

## Security Considerations

### Input Validation

```python
# Server-side validation
class UserCreate(UserBase):
    password: Annotated[
        str,
        Field(
            min_length=8,
            pattern=r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&])[A-Za-z\d@$!%*?&]",
            description="Password must contain uppercase, lowercase, number, and special character"
        )
    ]
```

### Rate Limiting

```python
# Protect registration endpoint
@router.post("/user", dependencies=[Depends(rate_limiter_dependency)])
async def write_user(user: UserCreate, db: AsyncSession):
    # Registration logic
    pass

# Protect login endpoint
@router.post("/login", dependencies=[Depends(rate_limiter_dependency)])
async def login_for_access_token():
    # Login logic
    pass
```

### Data Sanitization

```python
def sanitize_user_input(user_data: dict) -> dict:
    """Sanitize user input to prevent XSS and injection."""
    import html
    
    sanitized = {}
    for key, value in user_data.items():
        if isinstance(value, str):
            # HTML escape
            sanitized[key] = html.escape(value.strip())
        else:
            sanitized[key] = value
    
    return sanitized
```

## Next Steps

Now that you understand user management:

1. **[Permissions](permissions.md)** - Learn about role-based access control and authorization
2. **[Production Guide](../production.md)** - Implement production-grade security measures
3. **[JWT Tokens](jwt-tokens.md)** - Review token management if needed

User management provides the core functionality for authentication systems. Master these patterns before implementing advanced permission systems.

## Common Authentication Tasks

### Protect New Endpoints

```python
# Add authentication dependency to your router
@router.get("/my-endpoint")
async def my_endpoint(current_user: dict = Depends(get_current_user)):
    # Endpoint now requires authentication
    return {"user_specific_data": f"Hello {current_user['username']}"}

# Optional authentication for public endpoints
@router.get("/public-endpoint") 
async def public_endpoint(user: dict | None = Depends(get_optional_user)):
    if user:
        return {"message": f"Hello {user['username']}", "premium_features": True}
    return {"message": "Hello anonymous user", "premium_features": False}
```

### Complete Authentication Flow

```python
# 1. User registration
user_data = UserCreate(
    name="John Doe",
    username="johndoe", 
    email="john@example.com",
    password="SecurePassword123!"
)
user = await crud_users.create(db=db, object=user_data)

# 2. User login
form_data = {"username": "johndoe", "password": "SecurePassword123!"}
user = await authenticate_user(form_data["username"], form_data["password"], db)

# 3. Token generation (handled in login endpoint)
access_token = await create_access_token(data={"sub": user["username"]})
refresh_token = await create_refresh_token(data={"sub": user["username"]})

# 4. API access with token
headers = {"Authorization": f"Bearer {access_token}"}
response = requests.get("/api/v1/users/me", headers=headers)

# 5. Token refresh when access token expires
response = requests.post("/api/v1/refresh")  # Uses refresh token cookie
new_access_token = response.json()["access_token"]

# 6. Secure logout (blacklists both tokens)  
await logout_user(access_token=access_token, refresh_token=refresh_token, db=db)
```

### Check User Permissions

```python
def check_user_permission(user: dict, required_tier: str = None):
    """Check if user has required permissions."""
    if not user.get("is_active", True):
        raise UnauthorizedException("User account is disabled")
    
    if required_tier and user.get("tier", {}).get("name") != required_tier:
        raise ForbiddenException(f"Requires {required_tier} tier")

# Usage in endpoint
@router.get("/premium-feature")
async def premium_feature(current_user: dict = Depends(get_current_user)):
    check_user_permission(current_user, "Pro")
    return {"premium_data": "exclusive_content"}
```

### Custom Authentication Logic

```python
async def get_user_with_posts(current_user: dict = Depends(get_current_user)):
    """Custom dependency that adds user's posts."""
    posts = await crud_posts.get_multi(db=db, created_by_user_id=current_user["id"])
    current_user["posts"] = posts
    return current_user

# Usage
@router.get("/dashboard")
async def get_dashboard(user_with_posts: dict = Depends(get_user_with_posts)):
    return {
        "user": user_with_posts,
        "post_count": len(user_with_posts["posts"])
    }
``` 