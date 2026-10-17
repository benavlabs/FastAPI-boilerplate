"""Signing in on a password hash another system wrote, which ``legacy_verifiers`` accepts.

The project configures none, so each test wires the verifier it is about, the way
``infrastructure/auth/setup.py`` would for a migration.
"""

import bcrypt
import pytest
from crudauth.utils import verify_password, verify_plain_bcrypt
from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.auth.setup import auth as crud_auth
from src.modules.user.models import User

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("fresh_login_lockout")]


async def _store_a_plain_bcrypt_hash(db_session: AsyncSession, user: dict) -> str:
    """Give the account the hash the system it is migrating from would have written."""
    legacy = bcrypt.hashpw(user["password"].encode(), bcrypt.gensalt()).decode()
    await db_session.execute(update(User).where(User.id == user["id"]).values(hashed_password=legacy))
    await db_session.commit()
    return legacy


async def _stored_hash(db_session: AsyncSession, user: dict) -> str:
    row = (await db_session.execute(select(User).where(User.id == user["id"]))).scalar_one()
    await db_session.refresh(row)
    return row.hashed_password


async def _sign_in(client: AsyncClient, user: dict):
    return await client.post(
        "/api/v1/auth/login",
        data={"username": user["username"], "password": user["password"]},
    )


async def test_a_hash_crudauth_did_not_write_is_refused_while_no_verifier_is_configured(
    client: AsyncClient, db_session: AsyncSession, test_user: dict
):
    """crudauth bcrypts a digest of the password, so a plain bcrypt hash never matches its own check."""
    assert crud_auth.runtime.legacy_verifiers == ()
    await _store_a_plain_bcrypt_hash(db_session, test_user)

    assert (await _sign_in(client, test_user)).status_code == 401


async def test_a_legacy_hash_signs_in_and_is_replaced_with_a_crudauth_one(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, monkeypatch
):
    monkeypatch.setattr(crud_auth.runtime, "legacy_verifiers", (verify_plain_bcrypt,))
    legacy = await _store_a_plain_bcrypt_hash(db_session, test_user)

    response = await _sign_in(client, test_user)

    assert response.status_code == 200
    stored = await _stored_hash(db_session, test_user)
    assert stored != legacy
    assert verify_password(test_user["password"], stored)


async def test_the_account_no_longer_needs_the_verifier_after_that_first_sign_in(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, monkeypatch
):
    """Which is why the verifier is kept only until every account has signed in once."""
    monkeypatch.setattr(crud_auth.runtime, "legacy_verifiers", (verify_plain_bcrypt,))
    await _store_a_plain_bcrypt_hash(db_session, test_user)
    assert (await _sign_in(client, test_user)).status_code == 200

    monkeypatch.setattr(crud_auth.runtime, "legacy_verifiers", ())

    assert (await _sign_in(client, test_user)).status_code == 200


async def test_a_wrong_password_is_still_refused_with_a_verifier_configured(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, monkeypatch
):
    monkeypatch.setattr(crud_auth.runtime, "legacy_verifiers", (verify_plain_bcrypt,))
    legacy = await _store_a_plain_bcrypt_hash(db_session, test_user)

    response = await client.post(
        "/api/v1/auth/login",
        data={"username": test_user["username"], "password": "not-the-password"},
    )

    assert response.status_code == 401
    assert await _stored_hash(db_session, test_user) == legacy
