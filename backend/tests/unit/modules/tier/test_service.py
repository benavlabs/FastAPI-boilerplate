"""Tests for tier service deletion rules."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.common.exceptions import TierNotFoundError, ValidationError
from src.modules.rate_limit.models import RateLimit
from src.modules.tier.crud import crud_tiers
from src.modules.tier.service import TierService

pytestmark = pytest.mark.asyncio

DELETE_METHODS = ["delete", "permanent_delete"]


@pytest.fixture
def tier_service() -> TierService:
    return TierService()


@pytest.mark.parametrize("method", DELETE_METHODS)
async def test_delete_rejects_tier_assigned_to_users(
    tier_service: TierService, db_session: AsyncSession, test_user: dict, test_tier: dict, method: str
):
    with pytest.raises(ValidationError, match="assigned to users"):
        await getattr(tier_service, method)(test_tier["name"], db_session)

    assert await crud_tiers.exists(db=db_session, name=test_tier["name"], is_deleted=False)


@pytest.mark.parametrize("method", DELETE_METHODS)
async def test_delete_rejects_tier_with_rate_limits(
    tier_service: TierService, db_session: AsyncSession, test_tier: dict, method: str
):
    db_session.add(RateLimit(tier_id=test_tier["id"], name="free_widgets", path="/api/v1/widgets", limit=10, period=60))
    await db_session.commit()

    with pytest.raises(ValidationError, match="has rate limits"):
        await getattr(tier_service, method)(test_tier["name"], db_session)

    assert await crud_tiers.exists(db=db_session, name=test_tier["name"], is_deleted=False)


async def test_soft_delete_marks_unreferenced_tier_deleted(
    tier_service: TierService, db_session: AsyncSession, test_tier: dict
):
    await tier_service.delete(test_tier["name"], db_session)

    assert not await crud_tiers.exists(db=db_session, name=test_tier["name"], is_deleted=False)
    assert await crud_tiers.exists(db=db_session, name=test_tier["name"])


async def test_permanent_delete_removes_unreferenced_tier(tier_service: TierService, db_session: AsyncSession, test_tier: dict):
    await tier_service.permanent_delete(test_tier["name"], db_session)

    assert not await crud_tiers.exists(db=db_session, name=test_tier["name"])


@pytest.mark.parametrize("method", DELETE_METHODS)
async def test_delete_missing_tier_raises_not_found(tier_service: TierService, db_session: AsyncSession, method: str):
    with pytest.raises(TierNotFoundError):
        await getattr(tier_service, method)("missing", db_session)
