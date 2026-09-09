"""Tests for the application lifespan built by lifespan_factory."""

from contextlib import ExitStack
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI

from src.infrastructure.app_factory import lifespan_factory
from src.infrastructure.config.settings import get_settings

pytestmark = pytest.mark.asyncio

TEARDOWN_NAMES = ("close_cache", "close_rate_limiter", "close_database")


@pytest.fixture
def lifespan_settings():
    """Settings with cache and rate limiting on, so every teardown branch runs."""
    settings = get_settings().model_copy()
    settings.CACHE_ENABLED = True
    settings.RATE_LIMITER_ENABLED = True
    return settings


@pytest.fixture
def patched_lifespan():
    """Patch every side effect of the lifespan and record teardown call order."""
    call_order: list[str] = []

    def recorder(name: str) -> AsyncMock:
        return AsyncMock(side_effect=lambda *args, **kwargs: call_order.append(name))

    auth = MagicMock()
    auth.initialize = AsyncMock()
    auth.shutdown = recorder("auth_shutdown")

    mocks = {
        "create_tables": AsyncMock(),
        "initialize_cache": AsyncMock(),
        "initialize_rate_limiter": AsyncMock(),
        "auth": auth,
    }
    for name in TEARDOWN_NAMES:
        mocks[name] = recorder(name)

    with ExitStack() as stack:
        for name, mock in mocks.items():
            stack.enter_context(patch(f"src.infrastructure.app_factory.{name}", mock))
        yield mocks, call_order


class TestLifespanDatabaseTeardown:
    """The lifespan must drain the connection pool on the way out."""

    async def test_disposes_engine_on_clean_shutdown(self, lifespan_settings, patched_lifespan):
        """close_database is awaited once after a normal shutdown."""
        mocks, _ = patched_lifespan
        lifespan = lifespan_factory(lifespan_settings)

        async with lifespan(FastAPI()):
            mocks["close_database"].assert_not_awaited()

        mocks["close_database"].assert_awaited_once()

    async def test_disposes_after_cache_and_rate_limiter(self, lifespan_settings, patched_lifespan):
        """Teardown runs in reverse order of setup, with the database last."""
        _, call_order = patched_lifespan
        lifespan = lifespan_factory(lifespan_settings)

        async with lifespan(FastAPI()):
            pass

        assert call_order == ["auth_shutdown", "close_cache", "close_rate_limiter", "close_database"]

    async def test_disposes_when_body_raises(self, lifespan_settings, patched_lifespan):
        """A failure while the app is serving still drains the pool."""
        mocks, _ = patched_lifespan
        lifespan = lifespan_factory(lifespan_settings)

        with pytest.raises(RuntimeError, match="boom"):
            async with lifespan(FastAPI()):
                raise RuntimeError("boom")

        mocks["close_database"].assert_awaited_once()

    async def test_disposes_when_startup_fails(self, lifespan_settings, patched_lifespan):
        """A failure partway through startup still drains the pool."""
        mocks, _ = patched_lifespan
        mocks["initialize_cache"].side_effect = RuntimeError("cache down")
        lifespan = lifespan_factory(lifespan_settings)

        with pytest.raises(RuntimeError, match="cache down"):
            async with lifespan(FastAPI()):
                pytest.fail("startup should not have completed")

        mocks["close_database"].assert_awaited_once()

    async def test_skips_dispose_without_database_settings(self, patched_lifespan):
        """Settings that carry no database config leave the engine alone."""
        mocks, _ = patched_lifespan
        lifespan = lifespan_factory(object())  # type: ignore[arg-type]

        async with lifespan(FastAPI()):
            pass

        mocks["close_database"].assert_not_awaited()
        mocks["create_tables"].assert_not_awaited()
