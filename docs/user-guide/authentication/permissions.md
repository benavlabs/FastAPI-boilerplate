# Permissions and Authorization

Authorization determines what authenticated users can do within your application. While authentication answers "who are you?", authorization answers "what can you do?". This section covers the permission system, access control patterns, and how to implement secure authorization in your endpoints.

## Understanding Authorization

Authorization is a multi-layered security concept that protects resources and operations based on user identity, roles, and contextual information. The boilerplate implements several authorization patterns to handle different security requirements.

### Authorization vs Authentication

**Authentication**: Verifies user identity - confirms the user is who they claim to be
**Authorization**: Determines user permissions - decides what the authenticated user can access

These work together: you must authenticate first (prove identity) before you can authorize (check permissions).

### Authorization Patterns

The system implements several common authorization patterns:

1. **Role-Based Access Control (RBAC)**: Users have roles (superuser, regular user) that determine permissions
2. **Resource Ownership**: Users can only access resources they own
3. **Tiered Access**: Different user tiers have different capabilities and limits
4. **Contextual Authorization**: Permissions based on request context (rate limits, time-based access)

## Core Authorization Patterns

### Superuser Permissions

Superusers have elevated privileges for administrative operations. This pattern is essential for system management but must be carefully controlled.

```python
from app.api.dependencies import get_current_superuser

# Superuser-only endpoint
@router.get("/admin/users/", dependencies=[Depends(get_current_superuser)])
async def get_all_users(
    db: AsyncSession = Depends(async_get_db)
) -> list[UserRead]:
    # Only superusers can access this endpoint
    users = await crud_users.get_multi(
        db=db,
        schema_to_select=UserRead,
        return_as_model=True
    )
    return users.data
```

**When to Use Superuser Authorization:**

- **User management operations**: Creating, deleting, or modifying other users
- **System configuration**: Changing application settings or configuration
- **Data export/import**: Bulk operations on sensitive data
- **Administrative reporting**: Access to system-wide analytics and logs

**Security Considerations:**

- **Minimal Assignment**: Only assign superuser status when absolutely necessary
- **Regular Audits**: Periodically review who has superuser access
- **Activity Logging**: Log all superuser actions for security monitoring
- **Time-Limited Access**: Consider temporary superuser elevation for specific tasks

### Resource Ownership

Resource ownership ensures users can only access and modify their own data. This is the most common authorization pattern in user-facing applications.

```python
@router.get("/posts/me/")
async def get_my_posts(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(async_get_db)
) -> list[PostRead]:
    # Get posts owned by current user
    posts = await crud_posts.get_multi(
        db=db,
        created_by_user_id=current_user["id"],
        schema_to_select=PostRead,
        return_as_model=True
    )
    return posts.data

@router.delete("/posts/{post_id}")
async def delete_post(
    post_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(async_get_db)
) -> dict[str, str]:
    # 1. Get the post
    post = await crud_posts.get(db=db, id=post_id)
    if not post:
        raise NotFoundException("Post not found")
    
    # 2. Check ownership
    if post["created_by_user_id"] != current_user["id"]:
        raise ForbiddenException("You can only delete your own posts")
    
    # 3. Delete the post
    await crud_posts.delete(db=db, id=post_id)
    return {"message": "Post deleted"}
```

**Ownership Validation Pattern:**

1. **Retrieve Resource**: Get the resource from the database
2. **Check Ownership**: Compare resource owner with current user
3. **Authorize or Deny**: Allow action if user owns resource, deny otherwise

### User Tiers and Rate Limiting

User tiers provide differentiated access based on subscription levels or user status. This enables business models with different feature sets for different user types.

```python
@router.post("/posts/", response_model=PostRead)
async def create_post(
    post: PostCreate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(async_get_db)
) -> PostRead:
    # Check rate limits based on user tier
    await check_rate_limit(
        resource="posts", 
        user_id=current_user["id"], 
        tier_id=current_user.get("tier_id"),
        db=db
    )
    
    # Create post with user association
    post_internal = PostCreateInternal(
        **post.model_dump(),
        created_by_user_id=current_user["id"]
    )
    
    created_post = await crud_posts.create(db=db, object=post_internal)
    return created_post
```

**Rate Limiting Implementation:**

```python
async def check_rate_limit(
    resource: str, 
    user_id: int, 
    tier_id: int | None, 
    db: AsyncSession
) -> None:
    # 1. Get user's tier information
    if tier_id:
        tier = await crud_tiers.get(db=db, id=tier_id)
        limit = tier["rate_limit_posts"] if tier else 10  # Default limit
    else:
        limit = 5  # Free tier limit
    
    # 2. Count recent posts (last 24 hours)
    recent_posts = await crud_posts.count(
        db=db,
        created_by_user_id=user_id,
        created_at__gte=datetime.utcnow() - timedelta(hours=24)
    )
    
    # 3. Check if limit exceeded
    if recent_posts >= limit:
        raise RateLimitException(f"Daily {resource} limit exceeded ({limit})")
```

**Tier-Based Authorization Benefits:**

- **Business Model Support**: Different features for different subscription levels  
- **Resource Protection**: Prevents abuse by limiting free tier usage
- **Progressive Enhancement**: Encourages upgrades by showing tier benefits
- **Fair Usage**: Ensures equitable resource distribution among users

### Custom Permission Helpers

Custom permission functions provide reusable authorization logic for complex scenarios.

```python
# Permission helper functions
async def can_edit_post(user: dict, post_id: int, db: AsyncSession) -> bool:
    """Check if user can edit a specific post."""
    post = await crud_posts.get(db=db, id=post_id)
    if not post:
        return False
    
    # Superusers can edit any post
    if user.get("is_superuser", False):
        return True
    
    # Users can edit their own posts
    if post["created_by_user_id"] == user["id"]:
        return True
    
    return False

async def can_access_admin_panel(user: dict) -> bool:
    """Check if user can access admin panel."""
    return user.get("is_superuser", False)

async def has_tier_feature(user: dict, feature: str, db: AsyncSession) -> bool:
    """Check if user's tier includes a specific feature."""
    tier_id = user.get("tier_id")
    if not tier_id:
        return False  # Free tier - no premium features
    
    tier = await crud_tiers.get(db=db, id=tier_id)
    if not tier:
        return False
    
    # Check tier features (example)
    return tier.get(f"allows_{feature}", False)

# Usage in endpoints
@router.put("/posts/{post_id}")
async def update_post(
    post_id: int,
    post_updates: PostUpdate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(async_get_db)
) -> PostRead:
    # Use permission helper
    if not await can_edit_post(current_user, post_id, db):
        raise ForbiddenException("Cannot edit this post")
    
    updated_post = await crud_posts.update(
        db=db, 
        object=post_updates, 
        id=post_id
    )
    return updated_post
```

**Permission Helper Benefits:**

- **Reusability**: Same logic used across multiple endpoints
- **Consistency**: Ensures uniform permission checking
- **Maintainability**: Changes to permissions only need updates in one place
- **Testability**: Permission logic can be unit tested separately

## Authorization Dependencies

### Basic Authorization Dependencies

```python
# Required authentication
async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(async_get_db)
) -> dict:
    """Get currently authenticated user."""
    token_data = await verify_token(token, TokenType.ACCESS, db)
    if not token_data:
        raise HTTPException(status_code=401, detail="Invalid token")
    
    user = await crud_users.get(db=db, username=token_data.username_or_email)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    
    return user

# Optional authentication
async def get_optional_user(
    token: str = Depends(optional_oauth2_scheme),
    db: AsyncSession = Depends(async_get_db)
) -> dict | None:
    """Get currently authenticated user, or None if not authenticated."""
    if not token:
        return None
    
    try:
        return await get_current_user(token=token, db=db)
    except HTTPException:
        return None

# Superuser requirement
async def get_current_superuser(
    current_user: dict = Depends(get_current_user)
) -> dict:
    """Get current user and ensure they are a superuser."""
    if not current_user.get("is_superuser", False):
        raise HTTPException(status_code=403, detail="Not enough permissions")
    return current_user
```

### Advanced Authorization Dependencies

```python
# Tier-based access control
def require_tier(minimum_tier: str):
    """Factory function for tier-based dependencies."""
    async def check_user_tier(
        current_user: dict = Depends(get_current_user),
        db: AsyncSession = Depends(async_get_db)
    ) -> dict:
        tier_id = current_user.get("tier_id")
        if not tier_id:
            raise HTTPException(status_code=403, detail="No subscription tier")
        
        tier = await crud_tiers.get(db=db, id=tier_id)
        if not tier or tier["name"] != minimum_tier:
            raise HTTPException(
                status_code=403, 
                detail=f"Requires {minimum_tier} tier"
            )
        
        return current_user
    
    return check_user_tier

# Resource ownership dependency
def require_resource_ownership(resource_type: str):
    """Factory function for resource ownership dependencies."""
    async def check_ownership(
        resource_id: int,
        current_user: dict = Depends(get_current_user),
        db: AsyncSession = Depends(async_get_db)
    ) -> dict:
        if resource_type == "post":
            resource = await crud_posts.get(db=db, id=resource_id)
            owner_field = "created_by_user_id"
        else:
            raise ValueError(f"Unknown resource type: {resource_type}")
        
        if not resource:
            raise HTTPException(status_code=404, detail="Resource not found")
        
        # Superusers can access any resource
        if current_user.get("is_superuser", False):
            return current_user
        
        # Check ownership
        if resource[owner_field] != current_user["id"]:
            raise HTTPException(
                status_code=403, 
                detail="You don't own this resource"
            )
        
        return current_user
    
    return check_ownership

# Usage examples
@router.get("/premium-feature", dependencies=[Depends(require_tier("Premium"))])
async def premium_feature():
    return {"message": "Premium feature accessed"}

@router.put("/posts/{post_id}")
async def update_post(
    post_id: int,
    post_update: PostUpdate,
    current_user: dict = Depends(require_resource_ownership("post")),
    db: AsyncSession = Depends(async_get_db)
) -> PostRead:
    # User ownership already verified by dependency
    updated_post = await crud_posts.update(db=db, object=post_update, id=post_id)
    return updated_post
```

## Security Best Practices

### Principle of Least Privilege

Always grant the minimum permissions necessary for users to complete their tasks.

**Implementation:**

- **Default Deny**: Start with no permissions and explicitly grant what's needed
- **Regular Review**: Periodically audit user permissions and remove unnecessary access
- **Role Segregation**: Separate administrative and user-facing permissions
- **Temporary Elevation**: Use temporary permissions for one-time administrative tasks

### Defense in Depth

Implement multiple layers of authorization checks throughout your application.

**Authorization Layers:**

1. **API Gateway**: Route-level permission checks
2. **Endpoint Dependencies**: FastAPI dependency injection for common patterns
3. **Business Logic**: Method-level permission validation
4. **Database**: Row-level security where applicable

### Input Validation and Sanitization

Always validate and sanitize user input, even from authorized users.

```python
@router.post("/admin/users/{user_id}/tier")
async def update_user_tier(
    user_id: int,
    tier_update: UserTierUpdate,
    current_user: dict = Depends(get_current_superuser),
    db: AsyncSession = Depends(async_get_db)
) -> dict[str, str]:
    # 1. Validate tier exists
    tier = await crud_tiers.get(db=db, id=tier_update.tier_id)
    if not tier:
        raise NotFoundException("Tier not found")
    
    # 2. Validate user exists
    user = await crud_users.get(db=db, id=user_id)
    if not user:
        raise NotFoundException("User not found")
    
    # 3. Prevent self-demotion (optional business rule)
    if user_id == current_user["id"] and tier["name"] == "free":
        raise ForbiddenException("Cannot demote yourself to free tier")
    
    # 4. Update user tier
    await crud_users.update(
        db=db, 
        object={"tier_id": tier_update.tier_id}, 
        id=user_id
    )
    
    return {"message": f"User tier updated to {tier['name']}"}
```

### Audit Logging

Log all significant authorization decisions for security monitoring and compliance.

```python
import logging

security_logger = logging.getLogger("security")

async def log_authorization_event(
    user_id: int,
    action: str,
    resource: str,
    result: str,
    details: dict = None
):
    """Log authorization events for security auditing."""
    security_logger.info(
        f"Authorization {result}: User {user_id} attempted {action} on {resource}",
        extra={
            "user_id": user_id,
            "action": action,
            "resource": resource,
            "result": result,
            "details": details or {}
        }
    )

# Usage in permission checks
async def delete_user_account(user_id: int, current_user: dict, db: AsyncSession):
    if current_user["id"] != user_id and not current_user.get("is_superuser"):
        await log_authorization_event(
            user_id=current_user["id"],
            action="delete_account",
            resource=f"user:{user_id}",
            result="denied",
            details={"reason": "insufficient_permissions"}
        )
        raise ForbiddenException("Cannot delete other users' accounts")
    
    await log_authorization_event(
        user_id=current_user["id"],
        action="delete_account", 
        resource=f"user:{user_id}",
        result="granted"
    )
    
    # Proceed with deletion
    await crud_users.delete(db=db, id=user_id)
```

## Common Authorization Patterns

### Multi-Tenant Authorization

For applications serving multiple organizations or tenants:

```python
@router.get("/organizations/{org_id}/users/")
async def get_organization_users(
    org_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(async_get_db)
) -> list[UserRead]:
    # Check if user belongs to organization
    membership = await crud_org_members.get(
        db=db,
        organization_id=org_id,
        user_id=current_user["id"]
    )
    
    if not membership:
        raise ForbiddenException("Not a member of this organization")
    
    # Check if user has admin role in organization
    if membership.role not in ["admin", "owner"]:
        raise ForbiddenException("Insufficient organization permissions")
    
    # Get organization users
    users = await crud_users.get_multi(
        db=db,
        organization_id=org_id,
        schema_to_select=UserRead,
        return_as_model=True
    )
    
    return users.data
```

### Time-Based Permissions

For permissions that change based on time or schedule:

```python
from datetime import datetime, time

async def check_business_hours_access(user: dict) -> bool:
    """Check if user can access during business hours only."""
    now = datetime.now()
    business_start = time(9, 0)  # 9 AM
    business_end = time(17, 0)   # 5 PM
    
    # Superusers can always access
    if user.get("is_superuser", False):
        return True
    
    # Regular users only during business hours
    current_time = now.time()
    return business_start <= current_time <= business_end

# Usage in dependency
async def require_business_hours(
    current_user: dict = Depends(get_current_user)
) -> dict:
    """Require access during business hours for non-admin users."""
    if not await check_business_hours_access(current_user):
        raise ForbiddenException("Access only allowed during business hours")
    return current_user

@router.post("/business-operation", dependencies=[Depends(require_business_hours)])
async def business_operation():
    return {"message": "Business operation completed"}
```

### Role-Based Access Control (RBAC)

For more complex permission systems:

```python
# Role definitions
class Role(str, Enum):
    USER = "user"
    MODERATOR = "moderator" 
    ADMIN = "admin"
    SUPERUSER = "superuser"

# Permission checking
def has_role(user: dict, required_role: Role) -> bool:
    """Check if user has required role or higher."""
    role_hierarchy = {
        Role.USER: 0,
        Role.MODERATOR: 1,
        Role.ADMIN: 2,
        Role.SUPERUSER: 3
    }
    
    user_role = Role(user.get("role", "user"))
    return role_hierarchy[user_role] >= role_hierarchy[required_role]

# Role-based dependency
def require_role(minimum_role: Role):
    """Factory for role-based dependencies."""
    async def check_role(current_user: dict = Depends(get_current_user)) -> dict:
        if not has_role(current_user, minimum_role):
            raise HTTPException(
                status_code=403,
                detail=f"Requires {minimum_role.value} role or higher"
            )
        return current_user
    
    return check_role

# Usage
@router.delete("/posts/{post_id}", dependencies=[Depends(require_role(Role.MODERATOR))])
async def moderate_delete_post(post_id: int, db: AsyncSession = Depends(async_get_db)):
    await crud_posts.delete(db=db, id=post_id)
    return {"message": "Post deleted by moderator"}
```

### Feature Flags and Permissions

For gradual feature rollouts:

```python
async def has_feature_access(user: dict, feature: str, db: AsyncSession) -> bool:
    """Check if user has access to a specific feature."""
    # Check feature flags
    feature_flag = await crud_feature_flags.get(db=db, name=feature)
    if not feature_flag or not feature_flag.enabled:
        return False
    
    # Check user tier permissions
    if feature_flag.requires_tier:
        tier_id = user.get("tier_id")
        if not tier_id:
            return False
        
        tier = await crud_tiers.get(db=db, id=tier_id)
        if not tier or tier["level"] < feature_flag["minimum_tier_level"]:
            return False
    
    # Check beta user status
    if feature_flag.beta_only:
        return user.get("is_beta_user", False)
    
    return True

# Feature flag dependency
def require_feature(feature_name: str):
    """Factory for feature flag dependencies."""
    async def check_feature_access(
        current_user: dict = Depends(get_current_user),
        db: AsyncSession = Depends(async_get_db)
    ) -> dict:
        if not await has_feature_access(current_user, feature_name, db):
            raise HTTPException(
                status_code=403,
                detail=f"Access to {feature_name} feature not available"
            )
        return current_user
    
    return check_feature_access

@router.get("/beta-feature", dependencies=[Depends(require_feature("beta_analytics"))])
async def get_beta_analytics():
    return {"analytics": "beta_data"}
```

This comprehensive permissions system provides flexible, secure authorization patterns that can be adapted to your specific application requirements while maintaining security best practices.
