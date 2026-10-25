"""The script that names the API keys an older version stored as scrypt, and revokes them."""

import logging
from typing import Any

import pytest
from sqlalchemy import Select, Update, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

import scripts.revoke_scrypt_api_keys as script
from scripts.revoke_scrypt_api_keys import revoke_scrypt_api_keys
from scripts.seed_errors import SeedError
from src.modules.api_keys.models import APIKey
from tests.unit.scripts.seed_helpers import run_script, script_environment

pytestmark = pytest.mark.asyncio

STORED_BY_AN_OLDER_VERSION = "scrypt$16384$8$1$c2FsdHk=$ZGVyaXZlZA=="
"""The shape of hash the script looks for; it matches by scheme and never verifies one."""

STORED_NOW = "sha256$" + "0" * 64


async def _insert_key(session: AsyncSession, user_id: int, name: str, key_hash: str) -> int:
    """An API key row holding the hash an older version of the service wrote."""
    key = APIKey(
        user_id=user_id,
        name=name,
        key_hash=key_hash,
        key_prefix=f"bp_{name}",
        permissions=[],
        usage_limits={},
    )
    session.add(key)
    await session.flush()

    return key.id


async def _is_active(session: AsyncSession, key_id: int) -> bool:
    active = await session.execute(select(APIKey.is_active).where(APIKey.id == key_id))

    return bool(active.scalar_one())


@pytest.fixture
def the_script_through_the_test_session(monkeypatch, db_session: AsyncSession):
    """The script reading and writing through the session the test reads."""

    class _Session:
        async def __aenter__(self):
            return db_session

        async def __aexit__(self, *args):
            return False

    monkeypatch.setattr(script, "local_session", _Session)


async def test_it_names_the_keys_stored_as_scrypt_and_revokes_none_of_them(
    the_script_through_the_test_session, db_session: AsyncSession, test_user: dict, caplog
):
    """Reporting is what a run without ``--revoke`` does, so an owner can be told first."""
    legacy = await _insert_key(db_session, test_user["id"], "legacy", STORED_BY_AN_OLDER_VERSION)
    await _insert_key(db_session, test_user["id"], "current", STORED_NOW)

    with caplog.at_level(logging.INFO):
        counted = await revoke_scrypt_api_keys()

    assert counted == (1, 0)
    assert await _is_active(db_session, legacy) is True
    assert f"API key {legacy} of user {test_user['id']} is stored as scrypt" in caplog.text
    assert "prefix bp_legacy" in caplog.text


async def test_revoking_deactivates_the_keys_stored_as_scrypt_and_nothing_else(
    the_script_through_the_test_session, db_session: AsyncSession, test_user: dict
):
    """A revoked row is not derived against, which is what ends the cost of the old hash."""
    legacy = await _insert_key(db_session, test_user["id"], "legacy", STORED_BY_AN_OLDER_VERSION)
    current = await _insert_key(db_session, test_user["id"], "current", STORED_NOW)

    counted = await revoke_scrypt_api_keys(revoking=True)

    assert counted == (1, 1)
    assert await _is_active(db_session, legacy) is False
    assert await _is_active(db_session, current) is True


async def test_running_it_again_revokes_nothing_and_still_names_the_keys(
    the_script_through_the_test_session, db_session: AsyncSession, test_user: dict
):
    """The hash stays as it is, so the key is reported until a migration drops the row."""
    await _insert_key(db_session, test_user["id"], "legacy", STORED_BY_AN_OLDER_VERSION)
    await revoke_scrypt_api_keys(revoking=True)

    assert await revoke_scrypt_api_keys(revoking=True) == (1, 0)


@pytest.mark.parametrize(
    ("refused", "says"),
    [
        (Select, "Could not read the API keys stored as scrypt"),
        (Update, "Could not revoke the API keys stored as scrypt"),
    ],
)
async def test_what_it_reports_names_the_statement_that_failed(
    the_script_through_the_test_session, db_session: AsyncSession, test_user: dict, monkeypatch, refused: Any, says: str
):
    """Reading the keys and revoking them fail for different reasons and read back as one."""
    await _insert_key(db_session, test_user["id"], "legacy", STORED_BY_AN_OLDER_VERSION)
    reached = db_session.execute

    async def refuse(statement, *arguments, **keywords):
        if isinstance(statement, refused):
            raise OperationalError(str(statement), {}, Exception("the connection dropped"))

        return await reached(statement, *arguments, **keywords)

    monkeypatch.setattr(db_session, "execute", refuse)

    with pytest.raises(SeedError, match=says):
        await revoke_scrypt_api_keys(revoking=True)


class TestTheScriptRunOnItsOwn:
    """``python scripts/revoke_scrypt_api_keys.py``, with no app to import the models for it."""

    async def test_it_revokes_the_key_it_finds(
        self, test_db_url: str, test_db_engine, db_session: AsyncSession, test_user: dict
    ):
        legacy = await _insert_key(db_session, test_user["id"], "legacy", STORED_BY_AN_OLDER_VERSION)
        await db_session.commit()

        completed = run_script("revoke_scrypt_api_keys", script_environment(test_db_url), "--revoke")

        assert completed.returncode == 0, completed.stdout + completed.stderr
        assert "Traceback" not in completed.stderr
        await db_session.rollback()
        assert await _is_active(db_session, legacy) is False

    async def test_an_argument_it_does_not_know_is_refused(self, test_db_url: str):
        """Revoking every key of a kind is not something a typo should be able to ask for."""
        completed = run_script("revoke_scrypt_api_keys", script_environment(test_db_url), "--revoke-all")

        assert completed.returncode == 2
        assert "Usage: python scripts/revoke_scrypt_api_keys.py [--revoke]" in completed.stdout + completed.stderr
