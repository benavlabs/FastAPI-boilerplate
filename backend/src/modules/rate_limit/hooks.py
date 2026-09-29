"""What the tier-limits feature plugs into other features, listed in ``wiring.hooks``."""

from contextlib import asynccontextmanager
from typing import Any

from crudauth import Principal
from crudauth.ratelimit import RateLimit
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.auth.setup import auth
from ...infrastructure.database.session import async_session
from .crud import crud_rate_limits
from .schemas import RateLimitSelect


async def tier_rate_limit(request: Request, principal: Principal | None) -> RateLimit | None:
    """The caller's configured limit for this path, when their tier has one.

    The row is read through the app's own database dependency, honoring any
    override on it, so the lookup uses the same database as the route it guards.
    """
    tier_id: Any = auth.repo.get(principal.user, "tier_id") if principal is not None and principal.user else None
    if tier_id is None:
        return None

    database = request.app.dependency_overrides.get(async_session, async_session)
    async with asynccontextmanager(database)() as db:
        configured = await crud_rate_limits.get(db=db, tier_id=tier_id, path=request.url.path, schema_to_select=RateLimitSelect)

    return RateLimit(configured["limit"], configured["period"]) if configured else None


async def rate_limits_reference_tier(tier: dict[str, Any], db: AsyncSession) -> str | None:
    """Refuse to delete a tier that still has rate limits, and say why."""
    if await crud_rate_limits.exists(db=db, tier_id=tier["id"]):
        return f"Cannot delete tier '{tier['name']}' because it has rate limits. Delete the rate limits first."

    return None
