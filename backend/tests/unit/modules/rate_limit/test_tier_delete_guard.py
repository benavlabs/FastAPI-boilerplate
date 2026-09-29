"""A tier that still has rate limits can't be deleted.

The refusal comes from the guard this feature contributes, so it is checked here
rather than with the tier service that merely asks its guards.
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.common.exceptions import ValidationError
from src.modules.rate_limit.models import RateLimit
from src.modules.tier.crud import crud_tiers
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
