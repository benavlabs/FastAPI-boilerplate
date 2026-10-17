"""The readiness checks really talk to the database."""

from pathlib import Path

import anyio
import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import Column, Integer, Table, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.infrastructure.config.settings import Settings, settings
from src.infrastructure.database import session as session_module
from src.infrastructure.database.health import (
    ALEMBIC_INI,
    database_is_reachable,
    every_declared_table_exists,
    expected_heads,
    readiness,
    schema_readiness,
    the_schema_is_current,
)
from src.infrastructure.database.session import Base
from tests.silent_server import silent_server

pytestmark = pytest.mark.asyncio


@pytest.fixture
def app_engine_on_the_test_database(monkeypatch, test_db_engine):
    """Point the app's own session factory at the test container."""
    factory = async_sessionmaker(bind=test_db_engine, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr(session_module, "_engine", test_db_engine)
    monkeypatch.setattr(session_module, "_session_factory", factory)


async def test_a_reachable_database_answers(app_engine_on_the_test_database):
    await database_is_reachable()


async def test_a_refused_connection_raises(monkeypatch):
    """The check has to fail, not answer ready, when nothing is listening."""
    monkeypatch.setattr(session_module, "_engine", None)
    monkeypatch.setattr(session_module, "_session_factory", None)
    nowhere = Settings(POSTGRES_SERVER="127.0.0.1", POSTGRES_PORT=1, POSTGRES_DB="nothing")
    monkeypatch.setattr(session_module, "get_settings", lambda: nowhere)

    with pytest.raises(Exception):
        await database_is_reachable()


async def test_a_database_that_never_answers_times_out(monkeypatch):
    """A real engine against a server that takes the connection and says nothing."""
    monkeypatch.setattr(session_module, "_engine", None)
    monkeypatch.setattr(session_module, "_session_factory", None)

    async with silent_server() as port:
        silent = Settings(POSTGRES_SERVER="127.0.0.1", POSTGRES_PORT=port, POSTGRES_DB="nothing")
        monkeypatch.setattr(session_module, "get_settings", lambda: silent)

        try:
            with pytest.raises(TimeoutError), anyio.fail_after(0.5):
                await database_is_reachable()
        finally:
            await session_module.dispose_engine()


async def test_the_check_names_the_database_it_probes():
    assert readiness.name == "database"
    assert readiness.target is not None
    target = readiness.target()
    assert target is not None and target.startswith("postgresql+asyncpg://")


@pytest.fixture
def a_declared_table_the_database_lacks():
    """A table the models declare and no database has, removed again afterwards."""
    ghost = Table("ghost_table", Base.metadata, Column("id", Integer, primary_key=True))

    yield ghost.name

    Base.metadata.remove(ghost)


async def test_a_database_holding_every_declared_table_answers(app_engine_on_the_test_database):
    await every_declared_table_exists()


async def test_a_database_missing_a_declared_table_raises(
    app_engine_on_the_test_database, a_declared_table_the_database_lacks: str
):
    """An unmigrated database answers ``SELECT 1`` and then fails every request that reads a row."""
    with pytest.raises(RuntimeError, match=a_declared_table_the_database_lacks):
        await every_declared_table_exists()


async def test_the_schema_check_is_asked_rather_than_mirrored():
    """It names no server, so the reachability check's answer is never reused for it."""
    assert schema_readiness.name == "schema"
    assert schema_readiness.target is None


@pytest.fixture
async def version_table(test_db_engine):
    """``alembic_version``, as a migrated database carries it, dropped again afterwards."""

    async def stamp(revision: str | None) -> None:
        async with test_db_engine.begin() as connection:
            await connection.execute(text("CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(32))"))
            await connection.execute(text("DELETE FROM alembic_version"))
            if revision is not None:
                await connection.execute(text("INSERT INTO alembic_version VALUES (:rev)"), {"rev": revision})

    yield stamp

    async with test_db_engine.begin() as connection:
        await connection.execute(text("DROP TABLE IF EXISTS alembic_version"))


@pytest.fixture
def carrying_one_revision(monkeypatch):
    """A project whose code carries a single migration, whatever this repository has."""
    monkeypatch.setattr("src.infrastructure.database.health.expected_heads", lambda: {"b0a1e5e7c0de"})
    monkeypatch.setattr(settings, "CREATE_TABLES_ON_STARTUP", False)


async def test_a_database_at_the_head_answers(app_engine_on_the_test_database, carrying_one_revision, version_table):
    await version_table("b0a1e5e7c0de")

    await the_schema_is_current()


async def test_a_database_behind_the_head_is_reported_with_both_revisions(
    app_engine_on_the_test_database, carrying_one_revision, version_table
):
    """A table check alone passes this database: the tables are all there, a column isn't."""
    await version_table("9999deadbeef")

    with pytest.raises(RuntimeError, match="is at 9999deadbeef, the code expects b0a1e5e7c0de"):
        await the_schema_is_current()


async def test_a_database_that_was_never_migrated_says_so(
    app_engine_on_the_test_database, carrying_one_revision, test_db_engine
):
    async with test_db_engine.begin() as connection:
        await connection.execute(text("DROP TABLE IF EXISTS alembic_version"))

    with pytest.raises(RuntimeError, match="never migrated"):
        await the_schema_is_current()


async def test_a_project_with_no_migrations_compares_the_tables(
    app_engine_on_the_test_database, a_declared_table_the_database_lacks: str, monkeypatch
):
    """Nothing to be at the head of, so the tables themselves are all there is to compare."""
    monkeypatch.setattr("src.infrastructure.database.health.expected_heads", set)

    with pytest.raises(RuntimeError, match=a_declared_table_the_database_lacks):
        await the_schema_is_current()


async def test_creating_tables_on_startup_compares_the_tables(
    app_engine_on_the_test_database, a_declared_table_the_database_lacks: str, monkeypatch
):
    """A development database built by ``create_all`` carries no ``alembic_version``."""
    monkeypatch.setattr("src.infrastructure.database.health.expected_heads", lambda: {"b0a1e5e7c0de"})
    monkeypatch.setattr(settings, "CREATE_TABLES_ON_STARTUP", True)

    with pytest.raises(RuntimeError, match=a_declared_table_the_database_lacks):
        await the_schema_is_current()


async def test_the_revisions_are_read_from_beside_the_source_tree(tmp_path, monkeypatch):
    """Not from the working directory the app was started in, which uvicorn decides."""
    monkeypatch.chdir(tmp_path)

    assert ALEMBIC_INI.exists()
    assert Path(ScriptDirectory.from_config(Config(str(ALEMBIC_INI))).dir) == ALEMBIC_INI.parent / "migrations"
    assert expected_heads() == set()
