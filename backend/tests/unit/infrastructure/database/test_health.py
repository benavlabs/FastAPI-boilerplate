"""The readiness check really talks to the database."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.infrastructure.config.settings import Settings
from src.infrastructure.database import session as session_module
from src.infrastructure.database.health import database_is_reachable, readiness

pytestmark = pytest.mark.asyncio


@pytest.fixture
def app_engine_on_the_test_database(monkeypatch, test_db_engine):
    """Point the app's own session factory at the test container."""
    factory = async_sessionmaker(bind=test_db_engine, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr(session_module, "_engine", test_db_engine)
    monkeypatch.setattr(session_module, "_session_factory", factory)


async def test_a_reachable_database_answers(app_engine_on_the_test_database):
    await database_is_reachable()


async def test_an_unreachable_database_raises(monkeypatch):
    """The check has to fail, not answer ready, when nothing is listening."""
    monkeypatch.setattr(session_module, "_engine", None)
    monkeypatch.setattr(session_module, "_session_factory", None)
    nowhere = Settings(POSTGRES_SERVER="127.0.0.1", POSTGRES_PORT=1, POSTGRES_DB="nothing")
    monkeypatch.setattr(session_module, "get_settings", lambda: nowhere)

    with pytest.raises(Exception):
        await database_is_reachable()


async def test_the_check_names_the_database_it_probes():
    assert readiness.name == "database"
    assert readiness.target is not None
    assert readiness.target().startswith("postgresql+asyncpg://")
