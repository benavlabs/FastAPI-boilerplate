"""The composition root: what the app mounts, starts and installs.

Hand-maintained until the generator exists: imports and literals only, so ruff,
mypy and an IDE see exactly what is wired.
"""

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Depends, FastAPI

from ..infrastructure.auth.dependencies import get_current_superuser
from ..infrastructure.auth.install import install as accounts_install
from ..infrastructure.auth.routes import router as auth_router
from ..infrastructure.auth.setup import auth
from ..infrastructure.auth.setup import lifecycle as accounts_lifecycle
from ..infrastructure.cache.initialize import lifecycle as cache_lifecycle
from ..infrastructure.composition import Lifecycle, RouterMount
from ..infrastructure.ratelimit.dependency import api_rate_limit_dependency
from ..interfaces.admin.initialize import install as admin_install
from ..modules.api_keys.routes import router as api_keys_router
from ..modules.rate_limit.routes import router as rate_limits_router
from ..modules.rate_limit.routes import user_rate_limits_router
from ..modules.tier.routes import router as tiers_router
from ..modules.tier.routes import user_tier_router
from ..modules.user.routes import router as users_router

ROUTER_MOUNTS: tuple[RouterMount, ...] = (
    RouterMount(users_router, "/users", throttled=True),
    RouterMount(user_tier_router, "/users", throttled=True),
    RouterMount(user_rate_limits_router, "/users", throttled=True),
    RouterMount(tiers_router, "/tiers", throttled=True),
    RouterMount(rate_limits_router, "/rate-limits", throttled=True),
    RouterMount(auth_router, "/auth", throttled=False),
    RouterMount(api_keys_router, "/api-keys", throttled=True),
)
ROOT_ROUTERS: tuple[APIRouter, ...] = (auth.oauth_router,) if auth.oauth is not None else ()
API_THROTTLE: tuple[Any, ...] = (Depends(api_rate_limit_dependency),)
LIFECYCLES: tuple[Lifecycle, ...] = (
    accounts_lifecycle,
    cache_lifecycle,
)
INSTALLERS: tuple[Callable[[FastAPI], None], ...] = (
    accounts_install,
    admin_install,
)
DOCS_GUARD: Callable[..., Any] | None = get_current_superuser
