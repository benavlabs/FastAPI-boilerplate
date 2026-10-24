"""A write that doesn't come back is reported as a server fault, not a conflict."""

import logging

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.common.exceptions import PersistenceError
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


async def test_anonymization_does_not_log_the_address(db_session: AsyncSession, test_user: dict, caplog):
    """The record keeps the email for compliance; the log has no reason to repeat it.

    The address travelled as a structured field rather than in the message, so this
    reads the fields the handler would emit, not the rendered text.
    """
    with caplog.at_level(logging.INFO):
        await UserService().anonymize_user(test_user["id"], db_session)

    anonymization = [record for record in caplog.records if "anonymization" in record.getMessage()]

    assert anonymization
    assert all(getattr(record, "email", None) is None for record in anonymization)
    assert all(test_user["email"] not in repr(record.__dict__) for record in anonymization)
    assert [getattr(record, "user_id", None) for record in anonymization] == [test_user["id"]] * len(anonymization)
