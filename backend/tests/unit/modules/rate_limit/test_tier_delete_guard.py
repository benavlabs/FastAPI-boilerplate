"""A tier that still has rate limits can't be deleted.

The refusal comes from the guard this feature contributes, so it is checked here
rather than with the tier service that merely asks its guards.
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.common.exceptions import ValidationError
from src.modules.rate_limit.crud import crud_rate_limits
from src.modules.rate_limit.models import RateLimit
from src.modules.rate_limit.schemas import RateLimitCreate
from src.modules.rate_limit.service import RateLimitService
from src.modules.tier.crud import crud_tiers
from src.modules.tier.exceptions import TierNotFoundError
from src.modules.tier.service import TierService

pytestmark = pytest.mark.asyncio

DELETE_METHODS = ["delete", "permanent_delete"]


@pytest.fixture
def tier_service() -> TierService:
    return TierService()


@pytest.mark.parametrize("method", DELETE_METHODS)
async def test_delete_rejects_tier_with_rate_limits(
    tier_service: TierService, db_session: AsyncSession, test_tier: dict, method: str
):
    db_session.add(RateLimit(tier_id=test_tier["id"], name="free_widgets", path="/api/v1/widgets", limit=10, period=60))
    await db_session.commit()

    with pytest.raises(ValidationError, match="has rate limits"):
        await getattr(tier_service, method)(test_tier["name"], db_session)

    assert await crud_tiers.exists(db=db_session, name=test_tier["name"], is_deleted=False)


async def test_a_rate_limit_cannot_be_created_for_a_deleted_tier(db_session: AsyncSession, test_tier: dict):
    """The tier is invisible everywhere else, so a limit for it would never apply."""
    await crud_tiers.delete(db=db_session, name=test_tier["name"])

    with pytest.raises(TierNotFoundError):
        await RateLimitService().create(RateLimitCreate(path="/api/v1/users", limit=5, period=60), test_tier["id"], db_session)


class TestATierHoldingOnlySoftDeletedLimits:
    """The rows are logically gone, and the tier's foreign key still points at them."""

    async def _with_a_deleted_limit(self, db_session: AsyncSession, test_tier: dict) -> None:
        db_session.add(RateLimit(tier_id=test_tier["id"], name="gone", path="/api/v1/widgets", limit=10, period=60))
        await db_session.commit()
        await crud_rate_limits.delete(db=db_session, name="gone")

    async def test_the_soft_delete_goes_through(self, tier_service: TierService, db_session: AsyncSession, test_tier: dict):
        await self._with_a_deleted_limit(db_session, test_tier)

        await tier_service.delete(test_tier["name"], db_session)

        assert not await crud_tiers.exists(db=db_session, name=test_tier["name"], is_deleted=False)

    async def test_the_permanent_delete_takes_them_with_it(
        self, tier_service: TierService, db_session: AsyncSession, test_tier: dict
    ):
        await self._with_a_deleted_limit(db_session, test_tier)

        await tier_service.permanent_delete(test_tier["name"], db_session)

        assert not await crud_tiers.exists(db=db_session, name=test_tier["name"])
        assert not await crud_rate_limits.exists(db=db_session, name="gone")

    async def test_a_live_limit_still_refuses_the_permanent_delete(
        self, tier_service: TierService, db_session: AsyncSession, test_tier: dict
    ):
        await self._with_a_deleted_limit(db_session, test_tier)
        db_session.add(RateLimit(tier_id=test_tier["id"], name="live", path="/api/v1/users/", limit=2, period=60))
        await db_session.commit()

        with pytest.raises(ValidationError, match="has rate limits"):
            await tier_service.permanent_delete(test_tier["name"], db_session)

        assert await crud_rate_limits.exists(db=db_session, name="live")
