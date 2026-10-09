"""One account per address, whatever case it was written in."""

import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.user.models import User

pytestmark = pytest.mark.asyncio

INDEX = "ix_user_email_lower"


def _user(username: str, email: str) -> User:
    return User(name=username.title(), username=username, email=email, hashed_password="hashed")


async def test_the_index_is_built_with_the_tables(test_db_engine):
    async with test_db_engine.connect() as connection:
        indexes = await connection.run_sync(lambda sync: inspect(sync).get_indexes("user"))

    built = next((index for index in indexes if index["name"] == INDEX), None)

    assert built is not None, sorted(index["name"] for index in indexes)
    assert built["unique"] is True
    assert built["expressions"] == ["lower(email::text)"]


async def test_the_same_address_in_another_case_cannot_be_stored(db_session: AsyncSession):
    db_session.add(_user("owner", "owner@example.com"))
    await db_session.flush()

    db_session.add(_user("other", "OWNER@example.com"))

    with pytest.raises(IntegrityError):
        await db_session.flush()
