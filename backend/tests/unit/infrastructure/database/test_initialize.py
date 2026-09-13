"""Tests for database resource teardown."""

from unittest.mock import AsyncMock, patch

import pytest

from src.infrastructure.database import session as session_module
from src.infrastructure.database.initialize import close_database

pytestmark = pytest.mark.asyncio


@pytest.fixture
def no_engine():
    """Run with a clean module state and restore whatever was there before."""
    previous_engine = session_module._engine
    previous_factory = session_module._session_factory
    session_module._engine = None
    session_module._session_factory = None

    yield

    session_module._engine = previous_engine
    session_module._session_factory = previous_factory


class TestCloseDatabase:
    """Test cases for close_database."""

    async def test_disposes_the_engine(self, no_engine):
        """close_database disposes the engine that was created."""
        engine = AsyncMock()
        session_module._engine = engine

        await close_database()

        engine.dispose.assert_awaited_once()

    async def test_keeps_the_engine_identity(self, no_engine):
        """Only the pool is drained, so long-lived holders stay valid."""
        engine = AsyncMock()
        factory = object()
        session_module._engine = engine
        session_module._session_factory = factory

        await close_database()

        assert session_module._engine is engine
        assert session_module._session_factory is factory

    async def test_is_a_no_op_without_an_engine(self, no_engine):
        """Nothing is built just to be disposed."""
        with patch.object(session_module, "build_engine") as build:
            await close_database()

            build.assert_not_called()

    async def test_is_safe_to_call_twice(self, no_engine):
        """Disposing an already disposed engine does not raise."""
        engine = AsyncMock()
        session_module._engine = engine

        await close_database()
        await close_database()

        assert engine.dispose.await_count == 2
