"""One live rule per tier and path.

Two of them left the limit a caller got to whichever row the lookup read first.
"""

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.modules.common.exceptions import ResourceExistsError
from src.modules.rate_limit.crud import crud_rate_limits
from src.modules.rate_limit.models import RateLimit
from src.modules.rate_limit.schemas import RateLimitCreate, RateLimitUpdate
from src.modules.rate_limit.service import RateLimitService

USERS = "/api/v1/users/"


@pytest.fixture
def rate_limit_service() -> RateLimitService:
    return RateLimitService()


def _a_rule(tier_id: int, name: str, path: str = USERS, limit: int = 10) -> RateLimit:
    return RateLimit(tier_id=tier_id, name=name, path=path, limit=limit, period=60)


async def test_a_second_live_rule_for_one_path_is_refused(db_session: AsyncSession, test_tier: dict):
    db_session.add(_a_rule(test_tier["id"], "first"))
    await db_session.commit()
    db_session.add(_a_rule(test_tier["id"], "second", limit=1000))

    with pytest.raises(IntegrityError):
        await db_session.commit()

    await db_session.rollback()


async def test_another_tier_configures_the_same_path(db_session: AsyncSession, test_tier: dict, second_test_tier: dict):
    db_session.add(_a_rule(test_tier["id"], "free_users"))
    db_session.add(_a_rule(second_test_tier["id"], "premium_users", limit=1000))

    await db_session.commit()

    assert await crud_rate_limits.count(db=db_session, path=USERS) == 2


async def test_creating_a_rule_for_a_configured_path_is_a_conflict(
    rate_limit_service: RateLimitService, db_session: AsyncSession, test_tier: dict
):
    await rate_limit_service.create(RateLimitCreate(path=USERS, limit=10, period=60), test_tier["id"], db_session)

    with pytest.raises(ResourceExistsError, match="already limits"):
        await rate_limit_service.create(RateLimitCreate(path=USERS, limit=1000, period=60), test_tier["id"], db_session)


async def test_moving_a_rule_onto_a_configured_path_is_a_conflict(
    rate_limit_service: RateLimitService, db_session: AsyncSession, test_tier: dict
):
    db_session.add(_a_rule(test_tier["id"], "users"))
    db_session.add(_a_rule(test_tier["id"], "tiers", path="/api/v1/tiers/"))
    await db_session.commit()

    with pytest.raises(ResourceExistsError, match="already limits"):
        await rate_limit_service.update("tiers", RateLimitUpdate(path=USERS), db_session)


async def test_a_rule_keeps_the_path_it_already_has(
    rate_limit_service: RateLimitService, db_session: AsyncSession, test_tier: dict
):
    """The row holding the path is this one, so sending it again changes nothing."""
    db_session.add(_a_rule(test_tier["id"], "users"))
    await db_session.commit()

    await rate_limit_service.update("users", RateLimitUpdate(path=USERS, limit=1000), db_session)

    assert (await rate_limit_service.get_by_name("users", db_session))["limit"] == 1000


async def test_a_deleted_rule_leaves_the_path_free_to_configure(
    rate_limit_service: RateLimitService, db_session: AsyncSession, test_tier: dict
):
    """The row is logically gone, so the path is one nothing configures."""
    created = await rate_limit_service.create(RateLimitCreate(path=USERS, limit=10, period=60), test_tier["id"], db_session)
    await crud_rate_limits.delete(db=db_session, name=created["name"])

    again = await rate_limit_service.create(RateLimitCreate(path=USERS, limit=1000, period=60), test_tier["id"], db_session)

    assert again["limit"] == 1000


async def test_a_rule_that_lands_after_the_check_is_a_conflict(
    rate_limit_service: RateLimitService,
    db_session: AsyncSession,
    test_db_engine,
    test_tier: dict,
    monkeypatch,
):
    """Another request configured the path between this one's check and its insert."""
    sessions = async_sessionmaker(test_db_engine, class_=AsyncSession, expire_on_commit=False)
    asked = crud_rate_limits.exists

    async def answering_then_colliding(*, db: AsyncSession, **filters):
        answer = await asked(db=db, **filters)
        if "path" in filters:
            async with sessions() as other:
                other.add(_a_rule(test_tier["id"], "landed", limit=1000))
                await other.commit()

        return answer

    monkeypatch.setattr(crud_rate_limits, "exists", answering_then_colliding)

    with pytest.raises(ResourceExistsError, match="Another rate limit"):
        await rate_limit_service.create(RateLimitCreate(path=USERS, limit=10, period=60), test_tier["id"], db_session)

    monkeypatch.undo()
    assert await crud_rate_limits.count(db=db_session, path=USERS) == 1
