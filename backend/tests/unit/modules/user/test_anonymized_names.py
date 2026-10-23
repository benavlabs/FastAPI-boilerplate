"""The name a deleted account takes, and what happens when something else holds it."""

import re
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.common.exceptions import PersistenceError
from src.modules.user.constants import USERNAME_PATTERN
from src.modules.user.crud import crud_users
from src.modules.user.models import User
from src.modules.user.service import ANONYMIZATION_ATTEMPTS, UserService


async def _username_of(db: AsyncSession, user_id: int) -> str:
    name = await db.scalar(select(User.username).where(User.id == user_id))
    assert name is not None

    return name


async def test_the_name_a_deleted_account_takes_is_one_no_signup_can_hold(db_session: AsyncSession, test_user: dict):
    await UserService().anonymize_user(test_user["id"], db_session)

    taken = await _username_of(db_session, test_user["id"])

    assert taken.startswith(f"deleted-{test_user['id']}-")
    assert re.fullmatch(USERNAME_PATTERN, taken) is None


async def test_a_name_already_held_does_not_stop_the_deletion(db_session: AsyncSession, test_user: dict, monkeypatch):
    """Only another deleted account can hold one, and it keeps the name it has."""
    planted = iter([uuid.UUID(hex="a" * 32), uuid.UUID(hex="b" * 32)])
    real = uuid.uuid4
    monkeypatch.setattr(uuid, "uuid4", lambda: next(planted, real()))
    holder = User(
        name="Holder",
        username=f"deleted-{test_user['id']}-{'a' * 12}",
        email="holder@example.com",
        hashed_password="DELETED_INVALID_HASH",
    )
    db_session.add(holder)
    await db_session.commit()
    holder_id = holder.id

    await UserService().anonymize_user(test_user["id"], db_session)

    assert await _username_of(db_session, test_user["id"]) == f"deleted-{test_user['id']}-{'b' * 12}"
    assert await _username_of(db_session, holder_id) == f"deleted-{test_user['id']}-{'a' * 12}"


async def test_a_deletion_with_no_free_name_left_says_so(db_session: AsyncSession, test_user: dict, monkeypatch):
    """Every name it tried was held, so the account is still the account it was."""
    held = [f"{attempt:x}" for attempt in range(ANONYMIZATION_ATTEMPTS)]
    planted = iter([uuid.UUID(hex=digit * 32) for digit in held])
    real = uuid.uuid4
    monkeypatch.setattr(uuid, "uuid4", lambda: next(planted, real()))
    for digit in held:
        db_session.add(
            User(
                name="Holder",
                username=f"deleted-{test_user['id']}-{digit * 12}",
                email=f"holder-{digit}@example.com",
                hashed_password="DELETED_INVALID_HASH",
            )
        )
    await db_session.commit()

    with pytest.raises(PersistenceError):
        await UserService().anonymize_user(test_user["id"], db_session)

    assert await _username_of(db_session, test_user["id"]) == test_user["username"]


async def test_a_refusal_from_another_index_is_not_a_held_name(db_session: AsyncSession, test_user: dict, monkeypatch):
    """Only the username index says the name is taken; anything else is nobody's to rename around."""
    tried = []

    class _Refusal(Exception):
        constraint_name = "ix_user_email_lower"

    async def refused(*args, **kwargs):
        tried.append(kwargs.get("object"))
        wrapped = Exception("duplicate key value violates a unique index")
        wrapped.__cause__ = _Refusal()
        raise IntegrityError("UPDATE user", {}, wrapped)

    monkeypatch.setattr(crud_users, "update", refused)

    with pytest.raises(IntegrityError):
        await UserService().anonymize_user(test_user["id"], db_session)

    assert len(tried) == 1
