"""Fixture users never collide, however many one test makes."""

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.user.models import User
from tests.fixtures import accounts


async def test_two_thousand_fixture_users_fit_in_one_session(db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch):
    """The password hash is stubbed: two thousand real ones take minutes, and the
    columns that must not collide are the username and the email."""
    monkeypatch.setattr(accounts, "get_password_hash", lambda password: "not-a-hash")
    users = [accounts.new_user(profile_image_url="https://example.com/test.jpg") for _ in range(2000)]
    db_session.add_all(users)
    await db_session.commit()

    stored = await db_session.scalar(select(func.count()).where(User.id.in_([user.id for user in users])))

    assert stored == 2000
