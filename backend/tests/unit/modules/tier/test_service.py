"""Tests for tier service deletion rules."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.common.exceptions import ValidationError
from src.modules.tier.crud import crud_tiers
from src.modules.tier.exceptions import TierNotFoundError
from src.modules.tier.schemas import TierUpdate, UserTierUpdate
from src.modules.tier.service import TierService
from src.modules.user.crud import crud_users

pytestmark = pytest.mark.asyncio

DELETE_METHODS = ["delete", "permanent_delete"]


@pytest.fixture
def tier_service() -> TierService:
    return TierService()


@pytest.mark.parametrize("method", DELETE_METHODS)
async def test_delete_rejects_tier_assigned_to_users(
    tier_service: TierService, db_session: AsyncSession, tiered_user: dict, test_tier: dict, method: str
):
    with pytest.raises(ValidationError, match="assigned to users"):
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


async def test_a_deleted_tier_cannot_be_assigned(
    tier_service: TierService, db_session: AsyncSession, test_user: dict, test_tier: dict
):
    """A tier nobody can list is not one a user can be put on."""
    await tier_service.delete(test_tier["name"], db_session)

    with pytest.raises(TierNotFoundError):
        await tier_service.update_user_tier(test_user["id"], UserTierUpdate(tier_id=test_tier["id"]), db_session)


async def test_a_deleted_tier_reads_as_no_tier(
    tier_service: TierService, db_session: AsyncSession, tiered_user: dict, test_tier: dict
):
    """The service refuses to delete a tier in use, so this is a row that raced or was imported."""
    await crud_tiers.delete(db=db_session, name=test_tier["name"])

    assert (await tier_service.get_for_user(tiered_user["id"], db_session))["tier"] is None


async def test_a_deleted_tier_cannot_be_renamed(tier_service: TierService, db_session: AsyncSession, test_tier: dict):
    """Nothing reads a deleted tier, so an update would edit a row users can't see."""
    await tier_service.delete(test_tier["name"], db_session)

    with pytest.raises(TierNotFoundError):
        await tier_service.update(test_tier["name"], TierUpdate(name="renamed"), db_session)

    assert await crud_tiers.exists(db=db_session, name=test_tier["name"])


@pytest.mark.parametrize("method", DELETE_METHODS)
async def test_a_tier_held_only_by_deleted_users_can_be_removed(
    tier_service: TierService, db_session: AsyncSession, tiered_user: dict, test_tier: dict, method: str
):
    """user.tier_id has no ondelete, so the rows have to be released first."""
    await crud_users.delete(db=db_session, id=tiered_user["id"])

    await getattr(tier_service, method)(test_tier["name"], db_session)

    released = await crud_users.get(db=db_session, id=tiered_user["id"])
    assert released is not None
    assert released["tier_id"] is None
    assert not await crud_tiers.exists(db=db_session, name=test_tier["name"], is_deleted=False)


async def test_a_live_user_still_keeps_the_tier(
    tier_service: TierService, db_session: AsyncSession, tiered_user: dict, test_tier: dict
):
    with pytest.raises(ValidationError, match="assigned to users"):
        await tier_service.permanent_delete(test_tier["name"], db_session)

    held = await crud_users.get(db=db_session, id=tiered_user["id"])
    assert held is not None
    assert held["tier_id"] == test_tier["id"]
