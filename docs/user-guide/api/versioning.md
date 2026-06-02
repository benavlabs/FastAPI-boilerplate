# API Versioning

The boilerplate ships a `v1` namespace under `/api/v1/`. This page documents the actual wiring and how to add `/api/v2/` when you need to make breaking changes.

## How It's Wired Today

```text
backend/src/interfaces/api/
├── __init__.py            # mounts /api → v1
└── v1/
    └── __init__.py        # mounts /v1 + each module's router
```

`interfaces/api/__init__.py`:

```python
from fastapi import APIRouter

from .v1 import router as v1_router

router = APIRouter(prefix="/api")
router.include_router(v1_router)
```

`interfaces/api/v1/__init__.py`:

```python
from fastapi import APIRouter

from ....infrastructure.auth.routes import router as auth_router
from ....modules.api_keys.routes import router as api_keys_router
from ....modules.rate_limit.routes import router as rate_limits_router
from ....modules.tier.routes import router as tiers_router
from ....modules.user.routes import router as users_router

router = APIRouter(prefix="/v1")
router.include_router(users_router, prefix="/users")
router.include_router(tiers_router, prefix="/tiers")
router.include_router(rate_limits_router, prefix="/rate-limits")
router.include_router(auth_router, prefix="/auth")
router.include_router(api_keys_router, prefix="/api-keys")
```

The aggregator is the **only** place that knows about every module's router. Each module exposes a single `router` from its `routes.py`, and v1 mounts them all under their respective prefixes.

`interfaces/main.py` then mounts the API tree:

```python
from ..interfaces.api import router

app.include_router(router)
```

So `users_router → /users → /v1/users → /api/v1/users → /api/v1/users/me`, etc.

## Endpoints Today

| URL prefix | Source |
|------------|--------|
| `/api/v1/users/*` | `modules/user/routes.py` |
| `/api/v1/tiers/*` | `modules/tier/routes.py` |
| `/api/v1/rate-limits/*` | `modules/rate_limit/routes.py` |
| `/api/v1/auth/*` | `infrastructure/auth/routes.py` |
| `/api/v1/api-keys/*` | `modules/api_keys/routes.py` |

## Adding `v2`

When you need to make breaking changes — new response shapes, removed fields, different auth requirements — add a new version sibling instead of mutating v1.

### Step 1: Create the v2 Aggregator

```bash
mkdir backend/src/interfaces/api/v2
touch backend/src/interfaces/api/v2/__init__.py
```

```python
# backend/src/interfaces/api/v2/__init__.py
from fastapi import APIRouter

# Import the v2-flavored route modules — see Step 2 below
from ....modules.user.routes_v2 import router as users_router

router = APIRouter(prefix="/v2")
router.include_router(users_router, prefix="/users")

# Re-export anything that didn't change in v2 from v1:
# from ....modules.tier.routes import router as tiers_router
# router.include_router(tiers_router, prefix="/tiers")
```

### Step 2: Create v2 Routes Per Module

Two patterns work, pick the one that fits the change:

**Pattern A: a separate `routes_v2.py`** — when v2's routes are different enough that mixing them in `routes.py` would be confusing.

```python
# backend/src/modules/user/routes_v2.py
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from fastcrud import PaginatedListResponse, compute_offset, paginated_response
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.auth.session.dependencies import get_current_user
from ...infrastructure.database.session import async_session
from .schemas_v2 import UserReadV2
from .service import UserService
from .routes import get_user_service  # reuse the service factory

router = APIRouter(tags=["Users (v2)"])


# v2 makes pagination mandatory and renames profile_image_url -> avatar_url
@router.get("/", response_model=PaginatedListResponse[UserReadV2])
async def list_users(
    db: Annotated[AsyncSession, Depends(async_session)],
    user_service: Annotated[UserService, Depends(get_user_service)],
    page: int = 1,
    items_per_page: int = 10,
) -> dict[str, Any]:
    result = await user_service.get_paginated_v2(
        skip=compute_offset(page, items_per_page),
        limit=items_per_page,
        db=db,
    )
    return paginated_response(crud_data=result, page=page, items_per_page=items_per_page)
```

**Pattern B: alias the existing router** — when v2's behavior is identical and only the URL prefix needs to differ:

```python
# backend/src/interfaces/api/v2/__init__.py
from ....modules.tier.routes import router as tiers_router

router.include_router(tiers_router, prefix="/tiers")
```

### Step 3: Mount v2 Alongside v1

```python
# backend/src/interfaces/api/__init__.py
from fastapi import APIRouter

from .v1 import router as v1_router
from .v2 import router as v2_router

router = APIRouter(prefix="/api")
router.include_router(v1_router)
router.include_router(v2_router)
```

Both `/api/v1/users/` and `/api/v2/users/` are now live.

## Schema Versioning

Keep v1 schemas exactly as they are; add v2 schemas in a new file. Never edit a v1 schema in a way that changes the wire format — that's the whole point of having a v2.

```python
# backend/src/modules/user/schemas.py — UNCHANGED
class UserRead(BaseModel):
    id: int
    name: str
    username: str
    email: EmailStr
    profile_image_url: str
    tier_id: int | None
    is_superuser: bool = False
    email_verified: bool = False
    oauth_provider: str | None = None


# backend/src/modules/user/schemas_v2.py — NEW
class UserReadV2(BaseModel):
    id: int
    name: str
    username: str
    email: EmailStr
    avatar_url: str                          # renamed from profile_image_url
    subscription_tier: str | None            # changed from tier_id (int) to tier name
    is_superuser: bool = False
    email_verified: bool = False
    created_at: datetime                     # newly exposed
```

Service methods that produce the v2 shape live next to the v1 ones — `UserService.get_paginated` for v1, `UserService.get_paginated_v2` for v2 — so the service still owns the data assembly logic.

## Sharing Code Across Versions

The CRUD layer, services, and infrastructure are **shared**. Only the routes and schemas duplicate. That's the point — it's cheap to add a version because most of the codebase doesn't move.

```text
modules/user/
├── models.py            ← shared
├── crud.py              ← shared
├── service.py           ← shared (add v2-shaped methods if needed)
├── schemas.py           ← v1 schemas
├── schemas_v2.py        ← v2 schemas
├── routes.py            ← v1 routes
└── routes_v2.py         ← v2 routes
```

## Deprecating a Version

When v2 is ready and v1 should sunset:

### 1. Add a deprecation header to v1 endpoints

```python
# Inside a v1 route handler
@router.get("/", response_model=list[UserRead], deprecated=True)
async def list_users(
    response: Response,
    ...,
) -> list[dict[str, Any]]:
    response.headers["Deprecation"] = "true"
    response.headers["Sunset"] = "Wed, 31 Dec 2025 00:00:00 GMT"
    response.headers["Link"] = '</api/v2/users/>; rel="successor-version"'
    return await ...
```

The `Deprecation`, `Sunset`, and `Link` headers come from the IETF [API Deprecation](https://datatracker.ietf.org/doc/html/rfc8594) drafts — clients with HTTP-aware tooling pick them up automatically.

The `deprecated=True` flag also marks the endpoint in `/docs`.

### 2. Track v1 usage

If you have logging middleware or observability, slice request counts by `request.url.path.startswith("/api/v1/")` to know when v1 traffic is low enough to retire.

### 3. Remove v1 after sunset

When the sunset date passes and traffic is gone:

1. Delete `interfaces/api/v1/`
2. Delete the v1-only `schemas.py` blocks (or rename `schemas_v2.py` → `schemas.py`)
3. Delete v1-only service methods
4. Update `interfaces/api/__init__.py` to mount only v2

## Per-Version OpenAPI Documentation

By default, `/docs` shows every route. To split docs per version, mount each version as a sub-app with its own `FastAPI()` instance:

```python
# backend/src/interfaces/main.py — sketch
from fastapi import FastAPI

from .api.v1 import router as v1_router
from .api.v2 import router as v2_router

main = FastAPI(title="My API")

v1 = FastAPI(title="My API v1", version="1.0.0")
v1.include_router(v1_router)
main.mount("/api/v1", v1)

v2 = FastAPI(title="My API v2", version="2.0.0")
v2.include_router(v2_router)
main.mount("/api/v2", v2)
```

You'll get `/api/v1/docs` and `/api/v2/docs` independently. Note the boilerplate ships a single mounted app today — adopt this only when you genuinely need separate docs.

## Testing Multiple Versions

Once v2 exists, run the test suite against both:

```python
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_v1_users_returns_list(client: AsyncClient):
    resp = await client.get("/api/v1/users/")
    # whatever v1's contract is — list, paginated, etc.
    assert resp.status_code in {200, 401, 403}


@pytest.mark.asyncio
async def test_v2_users_paginated(client: AsyncClient):
    resp = await client.get("/api/v2/users/")
    assert resp.status_code == 200
    body = resp.json()
    assert "data" in body
    assert "total_count" in body
    assert "page" in body
```

## Best Practices

### What counts as a breaking change?

- Removing a field from a response
- Renaming a field
- Changing a field's type (e.g. `tier_id: int | None` → `tier_name: str`)
- Tightening validation in a way that previously-valid input now fails
- Adding a required request field
- Changing default behavior (e.g. unpaginated → paginated)
- Changing auth requirements

If you're not making a breaking change, just add the new field/feature to v1.

### Keep the URL pattern consistent

Always `/api/v{number}/resource`. Don't get clever with version-in-headers schemes — URL versioning is unambiguous to humans and to caches.

### Don't fork the service layer prematurely

If v2 only changes the response shape, derive the v2 dict from the same service method via a small adapter; only fork the service when business logic actually differs.

### Document changes in a changelog

Tag the v2 release with the list of breaking changes:

```markdown
## API v2

Breaking changes vs v1:
- `GET /users/` now returns `PaginatedListResponse` instead of `list[UserRead]`
- `UserRead.profile_image_url` renamed to `avatar_url`
- `UserRead.tier_id` (int) replaced with `subscription_tier` (string)
- `POST /users/` now requires authentication
- `UserCreate` now requires `accept_terms: bool`
```

A short, blunt list helps consumers migrate.

## What's Next

- **[Database Migrations](../database/migrations.md)** — Schema changes that may motivate a new API version
- **[Endpoints](endpoints.md)** — Patterns for routes
- **[Schemas](../database/schemas.md)** — Versioned shapes
