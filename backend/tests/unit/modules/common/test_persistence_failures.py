"""A write that doesn't come back is reported as a server fault, not a conflict."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.common.exceptions import PersistenceError
from src.modules.tier.crud import crud_tiers
from src.modules.tier.schemas import TierCreate
from src.modules.tier.service import TierService
from src.modules.user.crud import crud_users
from src.modules.user.schemas import UserCreate
from src.modules.user.service import UserService

pytestmark = pytest.mark.asyncio


async def test_user_create_raises_persistence_error(monkeypatch, db_session: AsyncSession):
    """A user insert that returns nothing must not be reported as an existing account."""

    async def returns_nothing(*args, **kwargs):
        return None

    monkeypatch.setattr(crud_users, "create", returns_nothing)
    user = UserCreate(name="Test User", username="freshuser", email="fresh.user@example.com", password="Str1ngst!")

    with pytest.raises(PersistenceError):
        await UserService().create(user, db_session)


async def test_tier_create_raises_persistence_error(monkeypatch, db_session: AsyncSession):
    """Same for a tier insert that comes back empty."""

    async def returns_nothing(*args, **kwargs):
        return None

    monkeypatch.setattr(crud_tiers, "create", returns_nothing)

    with pytest.raises(PersistenceError):
        await TierService().create(TierCreate(name="brand-new-tier"), db_session)
