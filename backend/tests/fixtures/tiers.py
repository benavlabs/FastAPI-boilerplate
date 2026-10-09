"""Fixtures of the tiers feature."""

import pytest_asyncio
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.tier.models import Tier
from src.modules.user.models import User


@pytest_asyncio.fixture
async def test_tier(db_session: AsyncSession):
    """Create a test tier."""
    tier = Tier(name="free", description="Free tier")
    db_session.add(tier)
    await db_session.commit()
    return {"id": tier.id, "name": tier.name}


@pytest_asyncio.fixture
async def second_test_tier(db_session: AsyncSession):
    """Create a second test tier."""
    tier = Tier(name="premium", description="Premium tier")
    db_session.add(tier)
    await db_session.commit()
    return {"id": tier.id, "name": tier.name}


@pytest_asyncio.fixture
async def tiered_user(db_session: AsyncSession, test_user: dict, test_tier: dict):
    """``test_user`` put on ``test_tier``.

    A user has no tier unless the tiers feature gives them one, so a test that
    needs the pairing asks for it.
    """
    await db_session.execute(update(User).where(User.id == test_user["id"]).values(tier_id=test_tier["id"]))
    await db_session.commit()

    return {**test_user, "tier_id": test_tier["id"]}
