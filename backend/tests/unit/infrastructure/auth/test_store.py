"""The database store: when it is built, and that both of its tables work on Postgres."""

import importlib
import os
import subprocess
import sys
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from crudauth import DatabaseStore
from crudauth.transports.session.schemas import SessionData
from sqlalchemy import MetaData

from src.infrastructure.auth.store import build_store, store_is_selected
from src.infrastructure.config.settings import settings
from src.infrastructure.database import registry
from src.infrastructure.database.session import Base

BACKEND = Path(__file__).resolve().parents[4]

_REPORT_THE_WIRING = """
import warnings, logging
warnings.simplefilter("ignore")
logging.disable(50)

from src.infrastructure.auth.setup import auth, session_transport
from src.infrastructure.auth.store import database_store
from src.infrastructure.database.session import Base

print(type(database_store).__name__)
print(session_transport.backend)
print(type(auth.rate_limiter).__name__)
print(",".join(sorted(name for name in Base.metadata.tables if name.startswith("crudauth"))))
print(auth.runtime.database_store is database_store)
"""


@pytest.mark.parametrize("backend", ["memory", "redis"])
def test_another_backend_selects_no_store(monkeypatch, backend: str):
    """The tables are declared whatever the backend; whether the store is used is the setting."""
    monkeypatch.setattr(settings, "SESSION_BACKEND", backend)
    monkeypatch.setattr(settings, "RATE_LIMITER_BACKEND", backend)

    assert store_is_selected() is False
    assert isinstance(build_store(metadata=MetaData()), DatabaseStore)


@pytest.mark.parametrize(("session_backend", "limiter_backend"), [("database", "memory"), ("memory", "database")])
def test_either_setting_on_its_own_builds_the_store(monkeypatch, session_backend: str, limiter_backend: str):
    """Declared on a metadata of its own here, so the app's schema is untouched."""
    monkeypatch.setattr(settings, "SESSION_BACKEND", session_backend)
    monkeypatch.setattr(settings, "RATE_LIMITER_BACKEND", limiter_backend)

    assert isinstance(build_store(metadata=MetaData()), DatabaseStore)


def test_the_app_schema_carries_both_tables():
    """Part of the schema, not of a runtime choice: a baseline holds them either way."""
    assert sorted(name for name in Base.metadata.tables if name.startswith("crudauth")) == [
        "crudauth_counters",
        "crudauth_store",
    ]


class TestBothTablesOnPostgres:
    """A store on its own metadata, against the test database."""

    @pytest.fixture
    async def store(self, test_db_engine) -> AsyncIterator[DatabaseStore]:
        """Tables of its own, created and dropped here.

        Not the schema's two: those belong to the project now, and dropping them would
        leave the database missing tables the models declare.
        """
        built = DatabaseStore(test_db_engine, store_table="probe_store", counter_table="probe_counters")
        await built.create_tables()

        yield built

        async with test_db_engine.begin() as connection:
            await connection.run_sync(built.metadata.drop_all)

    async def test_a_stored_value_comes_back(self, store: DatabaseStore):
        sessions = store.storage(prefix="test:sessions:")
        session = SessionData(user_id=7, ip_address="127.0.0.1", user_agent="pytest")

        handle = await sessions.create(session)
        stored = await sessions.get(handle, SessionData)

        assert stored is not None
        assert stored.user_id == 7
        assert await sessions.delete(handle) is True
        assert await sessions.get(handle, SessionData) is None

    async def test_a_counter_counts_and_resets(self, store: DatabaseStore):
        counters = store.rate_limiter(prefix="test:rl:")

        assert await counters.increment("login:ip:127.0.0.1", expiry=60) == 1
        assert await counters.increment("login:ip:127.0.0.1", expiry=60) == 2
        assert await counters.get_count("login:ip:127.0.0.1") == 2

        await counters.reset("login:ip:127.0.0.1")

        assert await counters.get_count("login:ip:127.0.0.1") in (None, 0)

    async def test_it_answers_a_ping(self, store: DatabaseStore):
        assert await store.rate_limiter().ping() is True


_REGISTER_WHAT_THE_WIRING_LISTS = """
import importlib
import warnings, logging
warnings.simplefilter("ignore")
logging.disable(50)

from src.wiring.tables import TABLE_MODULES

for name in TABLE_MODULES:
    importlib.import_module(name)

from src.infrastructure.database.session import Base

print(",".join(sorted(name for name in Base.metadata.tables if name.startswith("crudauth"))))
"""


@pytest.mark.parametrize("backend", ["memory", "redis", "database"])
def test_the_listed_modules_alone_register_the_tables(backend: str):
    """Nothing under ``src/modules`` is imported here, as in a migration that only reads metadata.

    ``wiring/tables.py`` names the store, so a migration describes its tables without
    depending on a route module to pull them in. Were it to, an autogenerated migration
    would quietly drop them the day that import went away.
    """
    environment = {**os.environ, "PYTHONPATH": str(BACKEND), "SESSION_BACKEND": backend, "RATE_LIMITER_BACKEND": backend}

    result = subprocess.run(
        [sys.executable, "-c", _REGISTER_WHAT_THE_WIRING_LISTS],
        cwd=BACKEND,
        env=environment,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "crudauth_counters,crudauth_store"


def test_import_models_imports_every_module_the_wiring_lists(monkeypatch):
    """The walk over ``src/modules`` is not what registers them."""
    imported: list[str] = []
    real_import = importlib.import_module

    def recording(name: str, *args, **kwargs):
        imported.append(name)

        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(registry.importlib, "import_module", recording)
    registry.import_models()

    assert set(registry.TABLE_MODULES) <= set(imported)
    assert registry.TABLE_MODULES == ("src.infrastructure.auth.store",)


@pytest.mark.parametrize("backend", ["memory", "redis"])
def test_another_backend_hands_crudauth_no_store_and_still_declares_the_tables(backend: str):
    """Cold, as the app starts: the store goes unused, while the schema holds both tables."""
    environment = {
        **os.environ,
        "PYTHONPATH": str(BACKEND),
        "SESSION_BACKEND": backend,
        "RATE_LIMITER_BACKEND": backend,
    }

    result = subprocess.run(
        [sys.executable, "-c", _REPORT_THE_WIRING], cwd=BACKEND, env=environment, capture_output=True, text=True
    )

    assert result.returncode == 0, result.stderr
    store_type, _, _, declared, handed_the_same = result.stdout.split()
    assert store_type == "NoneType"
    assert declared == "crudauth_counters,crudauth_store"
    assert handed_the_same == "True"


def test_the_settings_put_the_sessions_and_the_counters_in_the_database():
    """The whole wiring, in a process that read the settings cold."""
    environment = {
        **os.environ,
        "PYTHONPATH": str(BACKEND),
        "SESSION_BACKEND": "database",
        "RATE_LIMITER_BACKEND": "database",
    }

    result = subprocess.run(
        [sys.executable, "-c", _REPORT_THE_WIRING], cwd=BACKEND, env=environment, capture_output=True, text=True
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.split() == [
        "DatabaseStore",
        "database",
        "DatabaseRateLimiterBackend",
        "crudauth_counters,crudauth_store",
        "True",
    ]
