# API Exception Handling

The boilerplate has a deliberate two-layer exception model:

1. **Domain exceptions** raised by services (`modules/common/exceptions.py`)
2. **HTTP exceptions** raised by routes (`infrastructure/auth/http_exceptions.py`)

Plus an automatic mapping layer that translates one to the other so routes don't have to know about specific HTTP status codes for every domain failure.

## Domain Exceptions

Defined in `backend/src/modules/common/exceptions.py`. Services raise these — they describe *what went wrong*, not how to translate it to HTTP.

| Exception | Used when |
|-----------|-----------|
| `DomainError` | Base class for all domain errors |
| `ResourceNotFoundError` | A requested record doesn't exist |
| `ResourceExistsError` | A unique constraint would fail |
| `ValidationError` | Input doesn't satisfy a business rule |
| `PermissionDeniedError` | The current user can't perform this action |
| `UserNotFoundError` (extends `ResourceNotFoundError`) | Specific: user lookup failed |
| `UserExistsError` (extends `ResourceExistsError`) | Specific: duplicate username/email |
| `TierNotFoundError` (extends `ResourceNotFoundError`) | Specific: tier lookup failed |
| `RateLimitNotFoundError` (extends `ResourceNotFoundError`) | Specific: rate limit row missing |
| `InsufficientCreditsError` | Quota / credit balance hit zero |
| `UsageLimitExceededError` | API key usage limit hit |

```python
# modules/user/service.py
async def create(self, user: UserCreate, db: AsyncSession) -> dict[str, Any]:
    if await crud_users.exists(db=db, email=user.email):
        raise UserExistsError("Email already registered")

    if await crud_users.exists(db=db, username=user.username):
        raise UserExistsError("Username already taken")

    # ...
```

The service doesn't know or care that this becomes a `409 Conflict` over HTTP — that mapping happens elsewhere.

## HTTP Exceptions

Re-exported from FastCRUD in `backend/src/infrastructure/auth/http_exceptions.py`:

| Exception | Status |
|-----------|--------|
| `BadRequestException` | 400 |
| `UnauthorizedException` | 401 |
| `ForbiddenException` | 403 |
| `NotFoundException` | 404 |
| `DuplicateValueException` | 409 |
| `UnprocessableEntityException` | 422 |
| `RateLimitException` | 429 |
| `HTTPException` | base FastAPI class |
| `CSRFException` | 403 with `X-CSRF-Error: true` header (defined locally) |

Use these from routes when you have an HTTP-shaped failure and no service involvement (domain errors raised by services need no route-level handling — see the mapping layer below):

```python
from ...infrastructure.auth.http_exceptions import BadRequestException

@router.get("/")
async def search(q: str | None = None):
    if q is None:
        raise BadRequestException("Provide ?q=")
    # ...
```

## The Mapping Layer (Centralized)

`modules/common/utils/error_handler.py` bridges domain → HTTP errors globally.

### Global Handler (Automatic)

`register_exception_handlers(app)` is called in `infrastructure/app_factory.py` at startup. It installs:

- A `RequestValidationError` handler (Pydantic 422s) → returns a generic `Invalid request` message + a `support_id`
- A catch-all `DomainError` handler → maps to the right HTTP status **and message** via `EXCEPTION_MAPPING`, and returns that message + a `support_id`. The raw exception message is logged server-side, never sent.
- A `CatchAllErrorMiddleware` that converts truly unhandled exceptions into 500s with a `support_id`

This means: **any uncaught `DomainError` raised in a service automatically becomes a properly-shaped HTTP response.** Routes do *not* wrap service calls in try/except — they just let exceptions propagate:

```python
@router.post("/", response_model=UserRead, status_code=201)
async def create_user(
    user: UserCreate,
    db: AsyncSessionDep,
    user_service: UserServiceDep,
) -> dict[str, Any]:
    return await user_service.create(user, db)
```

If the service raises `UserExistsError`, the client gets a 422 with `"A user with this email or username already exists."` and a `support_id`; anything unexpected becomes a 500 with the generic message the same way.

### Manual Handler (Rare)

For a route that genuinely needs to intercept an exception itself - to recover, or to answer
something other than the mapping would - `handle_exception()` is still available:

```python
from ..common.exceptions import TierNotFoundError
from ..common.utils.error_handler import handle_exception


@router.get("/{name}/limits")
async def get_tier_limits(name: str, db: AsyncSessionDep, tier_service: TierServiceDep) -> dict[str, Any]:
    try:
        tier = await tier_service.get_by_name(name, db)
    except TierNotFoundError:
        return DEFAULT_LIMITS          # an unknown tier falls back instead of failing
    except Exception as e:
        http_exception = handle_exception(e)
        if http_exception:
            raise http_exception
        raise

    return tier["limits"]
```

`handle_exception()`:

- Returns the mapped `HTTPException` if `e` is a `DomainError`
- Returns `e` unchanged if it's already an `HTTPException`
- Returns `None` otherwise (route then raises a 500)

### The Default Mapping

The mapping in `modules/common/constants.py`:

```python
EXCEPTION_MAPPING: dict[type[DomainError], Callable[[str], HTTPException]] = {
    InsufficientCreditsError:  lambda m: HTTPException(status_code=402, detail=m or "Insufficient credits."),
    UserNotFoundError:         lambda m: NotFoundException("User not found."),
    TierNotFoundError:         lambda m: NotFoundException("The requested tier was not found."),
    RateLimitNotFoundError:    lambda m: NotFoundException("Rate limit configuration not found."),
    ResourceNotFoundError:     lambda m: NotFoundException("The requested resource was not found."),
    UserExistsError:           lambda m: DuplicateValueException("A user with this email or username already exists."),
    ResourceExistsError:       lambda m: DuplicateValueException("This resource already exists."),
    UsageLimitExceededError:   lambda m: RateLimitException("Usage limit exceeded."),
    ValidationError:           lambda m: UnprocessableEntityException("The request could not be processed."),
    PermissionDeniedError:     lambda m: ForbiddenException("You don't have permission for this action."),
}
```

Notice the messages **don't echo the raised exception's message** — every entry but `InsufficientCreditsError` answers with a fixed string, so a message naming a row the caller isn't entitled to know about can't reach them. The raised message goes to the logs, with the `support_id` from the response to correlate on. `map_exception` walks the exception's MRO, so a subclass gets its own message rather than its base's.

## Response Format

### Standard error

```json
{
  "detail": "User not found.",
  "support_id": "a1b2c3d4"
}
```

### Validation error (422)

```json
{
  "detail": "Invalid request. Please check your input and try again.",
  "support_id": "a1b2c3d4"
}
```

### `InsufficientCreditsError` (402) — exception

This is the one case where the original error message is preserved, because the frontend needs the credit info for upgrade prompts:

```json
{
  "detail": "Need 100 more credits to complete this operation",
  "support_id": "a1b2c3d4"
}
```

## Common Patterns

### Check Before Create

```python
# Service method — domain layer
async def create(self, user: UserCreate, db: AsyncSession) -> dict[str, Any]:
    if await crud_users.exists(db=db, email=user.email):
        raise UserExistsError("Email already registered")
    if await crud_users.exists(db=db, username=user.username):
        raise UserExistsError("Username already taken")
    # ...
```

The route doesn't need to know — `UserExistsError` becomes a 409 automatically.

### Permission Check

```python
async def update_profile(
    self, current_user: dict, target_username: str, values: UserUpdate, db: AsyncSession,
) -> None:
    if current_user["username"] != target_username and not current_user["is_superuser"]:
        raise PermissionDeniedError("You can only update your own profile")
    # ...
```

### Resource Lookup

```python
async def get_by_username(self, username: str, db: AsyncSession) -> dict[str, Any]:
    user = await crud_users.get(db=db, username=username, is_deleted=False)
    if user is None:
        raise UserNotFoundError(f"User '{username}' not found")
    return user
```

### Direct HTTP for non-domain failures

When the failure has no domain meaning (e.g. a missing query parameter combination), raise the HTTP exception directly:

```python
from ...infrastructure.auth.http_exceptions import BadRequestException


@router.get("/")
async def search(
    q: str | None = None,
    tag: str | None = None,
):
    if q is None and tag is None:
        raise BadRequestException("Provide either ?q= or ?tag=")
    # ...
```

## Adding a Custom Domain Exception

1. **Define the exception** in `modules/common/exceptions.py`:

    ```python
    class WidgetExceededError(DomainError):
        """Raised when a user tries to create more widgets than their tier allows."""
        pass
    ```

2. **Add a mapping** in `modules/common/constants.py`:

    ```python
    from .exceptions import WidgetExceededError

    EXCEPTION_MAPPING = {
        # ...existing entries...
        WidgetExceededError: lambda m: HTTPException(
            status_code=403, detail="You've hit your widget limit"
        ),
    }
    ```

3. **Raise it from your service**:

    ```python
    raise WidgetExceededError("Free tier limited to 10 widgets")
    ```

The global handler (and `handle_exception()`) picks up the new mapping automatically.

## Adding a Custom HTTP Exception

If you need an HTTP exception not already exported, define it in `infrastructure/auth/http_exceptions.py` like the existing `CSRFException`:

```python
class PaymentRequiredException(HTTPException):
    """402 Payment Required."""

    def __init__(self, detail: str = "Payment required") -> None:
        super().__init__(status_code=402, detail=detail)
```

Then re-export it via `__all__` and import it where needed.

## Security Considerations

### Generic Messages for Auth

The login flow in `infrastructure/auth/routes.py` delegates credential checking to the `crudauth` `auth` singleton. Its `authenticate_password` does a timing-equalized check and raises `UnauthorizedException("Incorrect username or password")` on bad credentials (and a `429` once the escalating lockout trips):

```python
# crudauth's hardened check: timing-equalized, disabled-account guard, escalating lockout
user = await auth.authenticate_password(db, form_data.username, form_data.password, request=request)
```

The message doesn't say "username not found" or "wrong password" — both would reveal whether the username exists.

### Hide Resource Existence

For protected resources the user shouldn't even know about, return 404 instead of 403:

```python
post = await crud_posts.get(db=db, id=post_id)
if post is None:
    raise NotFoundException("Post not found")

if post["author_id"] != current_user["id"]:
    # 404, not 403 — don't reveal the post exists
    raise NotFoundException("Post not found")
```

### Don't Leak Internal Details

The global handler is already defensive about this — it returns generic messages and writes the real error to logs with a `support_id`. The `support_id` is your handle for grep'ing logs when a user reports an issue.

## Testing Exceptions

The codebase uses `pytest-asyncio` and FastAPI's `TestClient` for route tests:

```python
@pytest.mark.asyncio
async def test_user_not_found(client: AsyncClient):
    resp = await client.get("/api/v1/users/not-a-user")
    assert resp.status_code == 404
    body = resp.json()
    assert body["detail"]
    assert "support_id" in body


@pytest.mark.asyncio
async def test_duplicate_email(client: AsyncClient):
    payload = {
        "name": "Test User",
        "username": "test1",
        "email": "test@example.com",
        "password": "Password123!",
    }
    await client.post("/api/v1/users/", json=payload)

    payload["username"] = "test2"  # different username, same email
    resp = await client.post("/api/v1/users/", json=payload)
    assert resp.status_code == 409
```

For service-level tests, just assert the right `DomainError` is raised:

```python
@pytest.mark.asyncio
async def test_create_duplicate_user_raises(db_session, existing_user):
    service = UserService()
    with pytest.raises(UserExistsError):
        await service.create(
            UserCreate(name="...", username=existing_user["username"], email="x@x.com", password="..."),
            db_session,
        )
```

## What's Next

- **[Versioning](versioning.md)** — Versioning strategy
- **[CRUD Operations](../database/crud.md)** — How services use CRUD
- **[Authentication](../authentication/index.md)** — Sessions, OAuth, API keys
