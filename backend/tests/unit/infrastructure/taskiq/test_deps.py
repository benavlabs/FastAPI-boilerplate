"""Tests for the worker's lazily created engine."""

from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.pool import NullPool

from src.infrastructure.taskiq import deps as deps_module
from src.infrastructure.taskiq.deps import dispose_taskiq_engine, get_taskiq_engine

pytestmark = pytest.mark.asyncio


@pytest.fixture
def no_engine():
    """Run with a clean module state and restore whatever was there before."""
    previous_engine = deps_module._engine
    previous_factory = deps_module._session_factory
    deps_module._engine = None
    deps_module._session_factory = None

    yield

    deps_module._engine = previous_engine
    deps_module._session_factory = previous_factory


class TestGetTaskiqEngine:
    """Test cases for get_taskiq_engine."""

    async def test_builds_through_the_shared_builder_with_null_pool(self, no_engine):
        """The worker's engine comes from the same builder as the API's."""
        with patch.object(deps_module, "build_engine") as build:
            get_taskiq_engine()

        build.assert_called_once_with(poolclass=NullPool)

    async def test_creates_the_engine_on_first_call(self, no_engine):
        """Importing the module must not open a connection."""
        assert deps_module._engine is None

        with patch.object(deps_module, "build_engine"):
            get_taskiq_engine()

        assert deps_module._engine is not None

    async def test_reuses_the_same_engine(self, no_engine):
        """Later calls hand back the cached engine."""
        with patch.object(deps_module, "build_engine") as build:
            first = get_taskiq_engine()
            second = get_taskiq_engine()

        assert first is second
        assert build.call_count == 1


class TestDisposeTaskiqEngine:
    """Test cases for dispose_taskiq_engine."""

    async def test_disposes_the_engine(self, no_engine):
        """Shutdown releases the worker's connections."""
        engine = AsyncMock()
        factory = object()
        deps_module._engine = engine
        deps_module._session_factory = factory

        await dispose_taskiq_engine()

        engine.dispose.assert_awaited_once()
        assert deps_module._engine is engine
        assert deps_module._session_factory is factory

    async def test_is_a_no_op_without_an_engine(self, no_engine):
        """A worker that never touched the database builds nothing on shutdown."""
        with patch.object(deps_module, "build_engine") as build:
            await dispose_taskiq_engine()

            build.assert_not_called()
