"""Creating tables outside the app has to know about every model.

A script imports almost nothing, so the metadata is empty unless table creation
loads the models itself. Only a cold interpreter can tell.
"""

import subprocess
import sys
from pathlib import Path

from src.infrastructure.database.session import Base

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
