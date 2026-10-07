"""The one-off repair for rows whose JSON columns hold what the schemas refuse."""

from typing import Any

import pytest
from sqlalchemy import JSON, select, update
from sqlalchemy.ext.asyncio import AsyncSession

import scripts.cleanup_api_key_json as script
from scripts.cleanup_api_key_json import cleanup_api_key_json
from src.modules.api_keys.models import APIKey
from tests.unit.scripts.seed_helpers import run_script, script_environment

pytestmark = pytest.mark.asyncio


async def _insert_key(session: AsyncSession, user_id: int, name: str, **columns) -> int:
    """An API key row whose JSON columns hold what an older version left in them."""
    key = APIKey(
        user_id=user_id,
        name=name,
        key_hash=f"hash-{name}",
        key_prefix="bp_test",
        permissions=[],
        usage_limits={},
    )
    session.add(key)
    await session.flush()

    if columns:
        await session.execute(update(APIKey).where(APIKey.id == key.id).values(**columns))

    return key.id


async def _values(session: AsyncSession, key_id: int) -> tuple[Any, Any]:
    row = await session.execute(select(APIKey.permissions, APIKey.usage_limits).where(APIKey.id == key_id))

    return tuple(row.one())


@pytest.fixture
def repair_through_the_test_session(monkeypatch, db_session: AsyncSession):
    """The repair writing through the session the test reads."""

    class _Session:
        async def __aenter__(self):
            return db_session

        async def __aexit__(self, *args):
            return False

    monkeypatch.setattr(script, "local_session", _Session)


async def test_a_null_column_becomes_the_empty_value_its_schemas_read(
    repair_through_the_test_session, db_session, test_user: dict
):
    key_id = await _insert_key(db_session, test_user["id"], "legacy", permissions=JSON.NULL, usage_limits=JSON.NULL)

    repaired = await cleanup_api_key_json()

    assert repaired == {"permissions": 1, "usage_limits": 1}
    assert await _values(db_session, key_id) == ([], {})


async def test_a_scope_stored_as_an_object_is_emptied(repair_through_the_test_session, db_session, test_user: dict):
    """The shape an older version stored names nothing the registry knows, so the key is unscoped."""
    key_id = await _insert_key(db_session, test_user["id"], "legacy scope", permissions={"conversations": ["read"]})

    repaired = await cleanup_api_key_json()

    assert repaired == {"permissions": 1, "usage_limits": 0}
    assert await _values(db_session, key_id) == ([], {})


async def test_a_scope_of_names_and_configured_limits_are_left_alone(
    repair_through_the_test_session, db_session, test_user: dict
):
    limits = {"requests_per_day": 1000}
    key_id = await _insert_key(db_session, test_user["id"], "configured", permissions=["user.read"], usage_limits=limits)

    repaired = await cleanup_api_key_json()

    assert repaired == {"permissions": 0, "usage_limits": 0}
    assert await _values(db_session, key_id) == (["user.read"], limits)


async def test_running_it_again_repairs_nothing(repair_through_the_test_session, db_session, test_user: dict):
    await _insert_key(db_session, test_user["id"], "legacy", permissions=JSON.NULL)

    await cleanup_api_key_json()

    assert await cleanup_api_key_json() == {"permissions": 0, "usage_limits": 0}


class TestTheScriptRunOnItsOwn:
    """``python scripts/cleanup_api_key_json.py``, with no app to import the models for it."""

    async def test_it_repairs_the_row_it_finds(
        self, test_db_url: str, test_db_engine, db_session: AsyncSession, test_user: dict
    ):
        key_id = await _insert_key(db_session, test_user["id"], "legacy", permissions=JSON.NULL, usage_limits=JSON.NULL)
        await db_session.commit()

        completed = run_script("cleanup_api_key_json", script_environment(test_db_url))

        assert completed.returncode == 0, completed.stdout + completed.stderr
        assert "Traceback" not in completed.stderr
        await db_session.rollback()
        assert await _values(db_session, key_id) == ([], {})
