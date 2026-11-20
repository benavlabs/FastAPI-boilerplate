"""What the tiers feature plugs into other features, listed in ``wiring.signup``."""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.config.settings import settings
from .crud import crud_tiers


async def default_tier(db: AsyncSession) -> dict[str, Any]:
    """The tier ``DEFAULT_TIER_NAME`` names, for a new account, or nothing while there is no such tier."""
    tier = await crud_tiers.get(db=db, name=settings.DEFAULT_TIER_NAME, is_deleted=False)

    return {"tier_id": tier["id"]} if tier else {}
