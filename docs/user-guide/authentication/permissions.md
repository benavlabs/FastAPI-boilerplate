# Permissions and Authorization

Authentication answers "who are you?". Authorization answers "what can you do?". This page covers the boilerplate's authorization patterns: superuser flags, resource ownership, tier-based limits, and API key permissions.

## Authorization Patterns

The boilerplate ships four overlapping mechanisms. Pick the one(s) that fit your use case.

| Pattern | Where it lives | When to use |
|---------|----------------|-------------|
| **Superuser flag** | `User.is_superuser` boolean | Admin-only operations |
| **Resource ownership** | Service-layer permission checks | "Users can only edit their own X" |
| **Tier-based limits** | `Tier` model + `RateLimit` rules | Subscription gating, rate limits |
| **API key permissions** | `KeyPermission` model (resource + action) | Programmatic access control |

These compose. A typical request goes through:

1. **Authentication** — session cookie (or API key) identifies *who*
2. **Coarse access** — superuser flag for admin endpoints
3. **Fine-grained access** — service-layer ownership / tier checks
4. **Rate limiting** — tier-based per-route limits (separate concern)

## Superuser Authorization

The User model has an `is_superuser: bool` column. Endpoints that should only be accessible to admins use the `get_current_superuser` dependency:

```python
from typing import Annotated, Any

from fastapi import APIRouter, Depends

from ...infrastructure.auth.dependencies import get_current_superuser

router = APIRouter()


@router.delete("/admin/users/{username}")
async def gdpr_anonymize(
    username: str,
    _: Annotated[dict[str, Any], Depends(get_current_superuser)],
) -> dict[str, str]:
    # Only superusers reach this code
    ...
```

The leading `_:` is the codebase convention for dependency-only parameters whose value isn't used.

`get_current_superuser` returns 401 if not authenticated and 403 if authenticated but not a superuser. See [Sessions](sessions.md) for the dependency reference.

### When to Use the Superuser Flag

- User management (create/delete other users)
- Tier assignment (`PATCH /api/v1/users/{username}/tier`)
- Rate limit configuration (`PATCH /api/v1/rate-limits/{name}`)
- GDPR data anonymization
- System configuration changes

### Bootstrapping the First Superuser

The first superuser is created by `scripts/setup_initial_data.py` from `ADMIN_*` env vars on first run:

```bash
cd backend
uv run python -m scripts.setup_initial_data
```

To grant superuser to an existing user, flip the column directly via the admin UI (`/admin`) or a one-off SQL update.

## Resource Ownership

Most "users can only modify their own data" rules belong in the **service layer**, not the route. The service raises a `PermissionDeniedError`, which the global handler maps to HTTP 403.

Real example from `modules/user/service.py`:

```python
from ..common.exceptions import PermissionDeniedError


async def verify_user_permission(
    self,
    current_user: dict[str, Any],
    target_username: str,
    action: str,
) -> None:
    """Raise PermissionDeniedError if current_user can't act on target_username."""
    if current_user["username"] != target_username and not current_user["is_superuser"]:
        raise PermissionDeniedError(f"Cannot {action} for another user")
```

Routes call this before dispatching the operation:

```python
# modules/user/routes.py
@router.patch("/{username}")
async def update_user_profile(
    username: str,
    values: UserUpdate,
    current_user: Annotated[dict[str, Any], Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(async_session)],
    user_service: Annotated[UserService, Depends(get_user_service)],
) -> dict[str, str]:
    try:
        await user_service.verify_user_permission(current_user, username, "update profile")
        # ...proceed with update...
```

The exception flows up to the global handler (registered in `infrastructure/app_factory.py`) which translates it via the `EXCEPTION_MAPPING` table — `PermissionDeniedError` → `ForbiddenException` (403). See [Exceptions](../api/exceptions.md) for the full mapping pipeline.

### Generic Ownership Pattern

For your own modules:

```python
# modules/widgets/service.py
from ..common.exceptions import PermissionDeniedError, ResourceNotFoundError


class WidgetService:
    async def delete(
        self, widget_id: int, current_user: dict[str, Any], db: AsyncSession,
    ) -> None:
        widget = await crud_widgets.get(db=db, id=widget_id)
        if widget is None:
            raise ResourceNotFoundError("Widget not found")

        if widget["owner_id"] != current_user["id"] and not current_user["is_superuser"]:
            raise PermissionDeniedError("Cannot delete another user's widget")

        await crud_widgets.delete(db=db, id=widget_id)
```

Three rules to follow:

1. **Service raises domain exceptions, not HTTP exceptions.** Lets the same logic be reused outside routes (admin scripts, tests, taskiq jobs).
2. **Superuser bypass is explicit.** `not current_user["is_superuser"]` makes the rule readable.
3. **Order: existence check first, then ownership.** A 404 is preferred to a 403 for resources the user shouldn't even know about — see the [Hide Resource Existence](../api/exceptions.md#hide-resource-existence) note.

## Tier-Based Authorization

Every user has a `tier_id` foreign key to the `Tier` model. The boilerplate ships **bare tiers** — just `name` and `description`, no built-in feature mapping or pricing logic. You decide what tiers mean.

### Reading the User's Tier

`User.tier` is loaded automatically via `lazy="selectin"`, so a fetched user record includes their tier:

```python
@router.get("/me", response_model=UserRead)
async def me(
    current_user: Annotated[dict[str, Any], Depends(get_current_user)],
) -> dict[str, Any]:
    # current_user["tier"] is the joined Tier dict (or None)
    return current_user
```

### Gating a Feature on Tier Name

For a simple feature gate, check the tier name directly in the service:

```python
async def export_data(self, current_user: dict[str, Any], db: AsyncSession) -> bytes:
    tier = current_user.get("tier") or {}
    if tier.get("name") not in {"pro", "enterprise"}:
        raise PermissionDeniedError("Data export requires the Pro or Enterprise tier")
    # ...generate export...
```

This works for "binary" features. For more complex models (per-feature quotas, multiple add-ons), consider building an entitlements system on top — that's outside the scope of the boilerplate.

### Tier-Based Rate Limits

Rate limiting *is* built-in: each `RateLimit` row binds a tier to a path with a `limit` and `period`. The middleware in `infrastructure/rate_limit/middleware.py` enforces these per request. See [Rate Limiting](../rate-limiting/index.md).

To configure rate limits for a tier:

```bash
# Create a rate limit (admin only)
curl -X POST http://localhost:8000/api/v1/rate-limits/ \
  -b superuser_cookies.txt \
  -H "Content-Type: application/json" \
  -H "X-CSRF-Token: <token>" \
  -d '{
    "tier_id": 2,
    "name": "pro_users",
    "path": "/api/v1/widgets/",
    "limit": 1000,
    "period": 60
  }'
```

## API Key Permissions

For programmatic access, API keys carry their own per-key permission model. Each key can have multiple `KeyPermission` rows, where a permission is `(resource, action, allow/deny, optional conditions)`.

### Permission Model

```python
# modules/api_keys/models.py
class KeyPermission(Base, TimestampMixin):
    __tablename__ = "key_permissions"

    api_key_id: Mapped[int] = mapped_column(ForeignKey("api_keys.id", ondelete="CASCADE"))
    resource: Mapped[KeyPermissionResource] = mapped_column(index=True)
    action: Mapped[KeyPermissionAction] = mapped_column(index=True)
    conditions: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)
    is_allowed: Mapped[bool] = mapped_column(Boolean, default=True)
```

### Resources and Actions

The `KeyPermissionResource` and `KeyPermissionAction` enums in `modules/api_keys/enums.py` define the shape of a permission row:

```python
class KeyPermissionResource(StrEnum):
    USER_PROFILE = "user_profile"
    ANALYTICS = "analytics"
    ADMIN = "admin"
    BILLING = "billing"
    API_KEYS = "api_keys"
    WILDCARD = "*"
    # ... plus a few legacy values inherited from the upstream template


class KeyPermissionAction(StrEnum):
    READ = "read"
    WRITE = "write"
    DELETE = "delete"
    CREATE = "create"
    UPDATE = "update"
    LIST = "list"
    ADMIN = "admin"
    WILDCARD = "*"
```

`*` is a wildcard — `(resource="*", action="*")` is full access; `(resource="user_profile", action="*")` is full access to the user_profile resource.

!!! info "Customize the enums"
    The enum values are starting points. Edit `modules/api_keys/enums.py` to match the resources and actions your API actually exposes. The default values include some leftovers from the upstream template (e.g. `conversations`, `credits`) — feel free to drop them.

### Granting Permissions on a New Key

Permissions are passed at creation time:

```bash
curl -X POST http://localhost:8000/api/v1/api-keys/ \
  -b cookies.txt \
  -H "Content-Type: application/json" \
  -H "X-CSRF-Token: <token>" \
  -d '{
    "name": "Read-only analytics integration",
    "permissions": {
      "analytics": ["read", "list"],
      "user_profile": ["read"]
    },
    "usage_limits": {}
  }'
```

The service translates the dict into `KeyPermission` rows.

### Checking Permissions in a Route

When a request comes in via API key, you can guard endpoints by required `(resource, action)`. The boilerplate doesn't ship a built-in `require_permission(...)` decorator — the API key flow is left flexible so you can wire it however suits your app:

```python
async def require_key_permission(
    resource: KeyPermissionResource,
    action: KeyPermissionAction,
    db: AsyncSession,
    api_key: dict[str, Any],
) -> None:
    has_permission = await crud_key_permissions.exists(
        db=db,
        api_key_id=api_key["id"],
        resource=resource,
        action=action,
        is_allowed=True,
    )
    # also check wildcards
    if not has_permission:
        has_wildcard = await crud_key_permissions.exists(
            db=db,
            api_key_id=api_key["id"],
            resource=KeyPermissionResource.WILDCARD,
            action=KeyPermissionAction.WILDCARD,
            is_allowed=True,
        )
        if not has_wildcard:
            raise PermissionDeniedError(f"API key lacks {resource}:{action}")
```

How API keys are authenticated (parsing the header, looking up the row, checking the status) is up to you — `KeyStatus` defines the lifecycle (`ACTIVE`, `INACTIVE`, `SUSPENDED`, `EXPIRED`, `REVOKED`).

## Combining Patterns

A real endpoint often uses several at once:

```python
@router.delete("/widgets/{widget_id}", status_code=204)
async def delete_widget(
    widget_id: int,
    current_user: Annotated[dict[str, Any], Depends(get_current_user)],   # 1. authn
    db: Annotated[AsyncSession, Depends(async_session)],
    widget_service: Annotated[WidgetService, Depends(get_widget_service)],
) -> None:
    try:
        # Service handles:
        #   2. Existence check
        #   3. Ownership check (superuser bypass)
        #   4. Tier feature gate (e.g. "delete requires Pro tier")
        await widget_service.delete(widget_id, current_user, db)
    except Exception as e:
        http_exc = handle_exception(e)
        if http_exc:
            raise http_exc
        raise HTTPException(status_code=500, detail="An unexpected error occurred")
```

The route stays trivial. Authorization rules accumulate in the service, where they're testable and reusable.

## Testing Authorization

Test the **service**, not the route, for permission rules — they're easier to set up and faster to run.

```python
import pytest
from src.modules.user.service import UserService
from src.modules.common.exceptions import PermissionDeniedError


@pytest.mark.asyncio
async def test_normal_user_cannot_update_other_users():
    service = UserService()
    current_user = {"username": "alice", "is_superuser": False}

    with pytest.raises(PermissionDeniedError):
        await service.verify_user_permission(current_user, "bob", "update profile")


@pytest.mark.asyncio
async def test_superuser_can_update_other_users():
    service = UserService()
    current_user = {"username": "alice", "is_superuser": True}

    # Should not raise
    await service.verify_user_permission(current_user, "bob", "update profile")
```

For end-to-end coverage, integration tests against `TestClient` exercise the full session-cookie + permission-check stack. See [Testing](../testing.md).

## Best Practices

### Keep authorization in services

Routes do dependency injection and HTTP shaping; services hold rules. If a `PermissionDeniedError` raise feels out of place in your service, that's a sign your service is doing more than business logic.

### Order checks: authn → existence → ownership → quota

```python
# 1. Authenticated? — done by the dependency
# 2. Resource exists?
if widget is None:
    raise ResourceNotFoundError(...)
# 3. User owns it?
if widget["owner_id"] != current_user["id"] and not current_user["is_superuser"]:
    raise PermissionDeniedError(...)
# 4. Quota / tier OK?
if not within_tier_limits(...):
    raise PermissionDeniedError(...)
```

This order prevents leaking existence (404 before 403) and keeps the cheap checks first.

### Don't reinvent rate limits

The built-in tier rate-limiter middleware is enforced before your route runs. Don't roll your own per-feature counters unless you need something the middleware can't express. See [Rate Limiting](../rate-limiting/index.md).

### Audit superuser actions

Superuser endpoints touch sensitive data. Log the actor + action server-side — the boilerplate's logging infrastructure (with `correlation_id` + `support_id`) makes this straightforward. See [Logging](../../user-guide/configuration/index.md) for the setup.

## Next Steps

- **[Sessions](sessions.md)** — How session-based authentication works
- **[Rate Limiting](../rate-limiting/index.md)** — Tier-based rate limit middleware
- **[Exceptions](../api/exceptions.md)** — How `PermissionDeniedError` becomes 403
- **[Production](../production.md)** — Hardening checklist
