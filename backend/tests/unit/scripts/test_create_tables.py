"""Creating tables outside the app has to know about every model.

A script imports almost nothing, so the metadata is empty unless table creation
loads the models itself. Only a cold interpreter can tell.
"""

import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import inspect

from src.infrastructure.database.session import Base, build_engine
from tests.unit.scripts.seed_helpers import run_script, script_environment

BACKEND = Path(__file__).resolve().parents[3]

_COLD_RUN = """
import asyncio
from unittest.mock import MagicMock, patch

from src.infrastructure.database import session

registered = []


class _Connection:
    async def run_sync(self, target):
        registered.append(sorted(session.Base.metadata.tables))


class _Transaction:
    async def __aenter__(self):
        return _Connection()

    async def __aexit__(self, *exception):
        return False


with patch.object(session, "get_engine", lambda: MagicMock(begin=_Transaction)):
    asyncio.run(session.create_tables())

print("TABLES:" + ",".join(registered[0]))
"""


def _tables_a_cold_run_creates() -> list[str]:
    result = subprocess.run([sys.executable, "-c", _COLD_RUN], cwd=BACKEND, capture_output=True, text=True, check=True)
    line = next(line for line in result.stdout.splitlines() if line.startswith("TABLES:"))

    return [table for table in line.removeprefix("TABLES:").split(",") if table]


def test_creating_tables_registers_every_model_the_app_has():
    assert _tables_a_cold_run_creates() == sorted(Base.metadata.tables)


@pytest.mark.asyncio
async def test_the_script_run_on_its_own_creates_the_tables(test_db_url: str, test_db_engine):
    """``cd backend && python scripts/create_tables.py``, as the documentation runs it.

    ``PYTHONPATH`` is left out of the environment, so the only thing that can make ``src``
    importable is the path setup at the top of the script.
    """
    engine = build_engine(test_db_url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
    await engine.dispose()

    environment = script_environment(test_db_url)
    del environment["PYTHONPATH"]

    completed = run_script("create_tables", environment)

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "Traceback" not in completed.stderr

    engine = build_engine(test_db_url)
    async with engine.connect() as connection:
        created = await connection.run_sync(lambda sync: sorted(inspect(sync).get_table_names()))
    await engine.dispose()

    assert created == sorted(Base.metadata.tables)
