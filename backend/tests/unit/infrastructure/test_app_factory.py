"""Unit tests for the application factory."""

from contextlib import ExitStack
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import APIRouter, FastAPI
from httpx import ASGITransport, AsyncClient

from src.infrastructure import app_factory
from src.infrastructure.auth.dependencies import get_current_superuser
from src.infrastructure.config.settings import EnvironmentOption, Settings, settings

DOCS_PATHS = ("/docs", "/redoc", "/openapi.json")
TEARDOWN_NAMES = ("close_cache", "close_database")


@pytest.mark.asyncio
async def test_startup_failure_surfaces_the_original_error(monkeypatch):
    """A failed startup must raise the failing step's exception, not a teardown one."""

    async def failing_create_tables() -> None:
        raise RuntimeError("db unreachable")

    monkeypatch.setattr(app_factory, "create_tables", failing_create_tables)

    lifespan = app_factory.lifespan_factory(settings, create_tables_on_startup=True)

    with pytest.raises(RuntimeError, match="db unreachable"):
        async with lifespan(FastAPI()):
            pass  # pragma: no cover - startup fails before the yield


@pytest.fixture
def lifespan_settings():
    """Settings with cache and rate limiting on, so every teardown branch runs."""
    lifespan_settings = settings.model_copy()
    lifespan_settings.CACHE_ENABLED = True
    lifespan_settings.RATE_LIMITER_ENABLED = True
    return lifespan_settings


@pytest.fixture
def patched_lifespan():
    """Patch every side effect of the lifespan and record teardown call order."""
    call_order: list[str] = []

    def recorder(name: str) -> AsyncMock:
        return AsyncMock(side_effect=lambda *args, **kwargs: call_order.append(name))

    auth = MagicMock()
    auth.initialize = AsyncMock()
    auth.shutdown = recorder("auth_shutdown")

    cache_redis_client = MagicMock()
    cache_redis_client.aclose = recorder("cache_redis_client_aclose")

    rate_limiter_redis_client = MagicMock()
    rate_limiter_redis_client.aclose = recorder("rate_limiter_redis_client_aclose")

    mocks = {
        "create_tables": AsyncMock(),
        "initialize_cache": AsyncMock(),
        "cache_redis_client": cache_redis_client,
        "rate_limiter_redis_client": rate_limiter_redis_client,
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
        lifespan = app_factory.lifespan_factory(lifespan_settings)

        async with lifespan(FastAPI()):
            mocks["close_database"].assert_not_awaited()

        mocks["close_database"].assert_awaited_once()

    async def test_teardown_runs_in_reverse_order_with_database_last(self, lifespan_settings, patched_lifespan):
        """Teardown runs in reverse order of setup, with the database last."""
        _, call_order = patched_lifespan
        lifespan = app_factory.lifespan_factory(lifespan_settings)

        async with lifespan(FastAPI()):
            pass

        assert call_order == [
            "auth_shutdown",
            "cache_redis_client_aclose",
            "rate_limiter_redis_client_aclose",
            "close_cache",
            "close_database",
        ]

    async def test_disposes_when_body_raises(self, lifespan_settings, patched_lifespan):
        """A failure while the app is serving still drains the pool."""
        mocks, _ = patched_lifespan
        lifespan = app_factory.lifespan_factory(lifespan_settings)

        with pytest.raises(RuntimeError, match="boom"):
            async with lifespan(FastAPI()):
                raise RuntimeError("boom")

        mocks["close_database"].assert_awaited_once()

    async def test_disposes_when_startup_fails(self, lifespan_settings, patched_lifespan):
        """A failure partway through startup still drains the pool."""
        mocks, _ = patched_lifespan
        mocks["initialize_cache"].side_effect = RuntimeError("cache down")
        lifespan = app_factory.lifespan_factory(lifespan_settings)

        with pytest.raises(RuntimeError, match="cache down"):
            async with lifespan(FastAPI()):
                pytest.fail("startup should not have completed")

        mocks["close_database"].assert_awaited_once()

    async def test_skips_dispose_without_database_settings(self, patched_lifespan):
        """Settings that carry no database config leave the engine alone."""
        mocks, _ = patched_lifespan
        lifespan = app_factory.lifespan_factory(object())  # type: ignore[arg-type]

        async with lifespan(FastAPI()):
            pass

        mocks["close_database"].assert_not_awaited()
        mocks["create_tables"].assert_not_awaited()


def _create_app(environment: EnvironmentOption, enable_docs_in_production: bool = False) -> FastAPI:
    return app_factory.create_application(
        router=APIRouter(),
        settings=Settings(ENVIRONMENT=environment, ENABLE_DOCS_IN_PRODUCTION=enable_docs_in_production),
    )


async def _statuses(app: FastAPI, paths: tuple[str, ...]) -> list[int]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        return [(await client.get(path)).status_code for path in paths]


async def _docs_statuses(app: FastAPI) -> list[int]:
    return await _statuses(app, DOCS_PATHS)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("environment", "enable_docs_in_production", "expected_status"),
    [
        (EnvironmentOption.LOCAL, False, 200),
        (EnvironmentOption.DEVELOPMENT, False, 200),
        (EnvironmentOption.STAGING, False, 401),
        (EnvironmentOption.PRODUCTION, False, 404),
        (EnvironmentOption.PRODUCTION, True, 401),
    ],
)
async def test_docs_access_for_anonymous_requests(environment, enable_docs_in_production, expected_status):
    app = _create_app(environment, enable_docs_in_production)

    assert await _docs_statuses(app) == [expected_status] * len(DOCS_PATHS)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("environment", "enable_docs_in_production"),
    [(EnvironmentOption.STAGING, False), (EnvironmentOption.PRODUCTION, True)],
)
async def test_gated_docs_are_served_to_superusers(environment, enable_docs_in_production):
    app = _create_app(environment, enable_docs_in_production)
    app.dependency_overrides[get_current_superuser] = lambda: {"id": 1, "is_superuser": True}

    assert await _docs_statuses(app) == [200] * len(DOCS_PATHS)


@pytest.mark.asyncio
async def test_gated_docs_use_the_configured_paths():
    """The protected docs router must serve at the configured URLs, not hardcoded ones."""
    custom_paths = ("/internal/docs", "/internal/redoc", "/internal/openapi.json")
    custom = Settings(
        ENVIRONMENT=EnvironmentOption.STAGING,
        DOCS_URL=custom_paths[0],
        REDOC_URL=custom_paths[1],
        OPENAPI_URL=custom_paths[2],
    )
    app = app_factory.create_application(router=APIRouter(), settings=custom)

    assert await _statuses(app, custom_paths) == [401, 401, 401]
    assert await _docs_statuses(app) == [404, 404, 404]

    app.dependency_overrides[get_current_superuser] = lambda: {"id": 1, "is_superuser": True}

    assert await _statuses(app, custom_paths) == [200, 200, 200]


class TestLifespanAuth:
    """crudauth is initialized on startup, after every connection is ready."""

    async def test_initializes_crudauth_on_startup(self, lifespan_settings, patched_lifespan):
        mocks, _ = patched_lifespan
        lifespan = app_factory.lifespan_factory(lifespan_settings)

        async with lifespan(FastAPI()):
            mocks["auth"].initialize.assert_awaited_once()
