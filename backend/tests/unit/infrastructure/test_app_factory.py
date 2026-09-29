"""Unit tests for the application factory."""

from collections.abc import Callable
from contextlib import ExitStack
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from crudauth.exceptions import UnauthorizedException
from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from httpx import ASGITransport, AsyncClient

from src.infrastructure import app_factory
from src.infrastructure.composition import Lifecycle
from src.infrastructure.config.settings import EnvironmentOption, Settings, settings

DOCS_PATHS = ("/docs", "/redoc", "/openapi.json")


async def _refuse() -> None:
    """A guard that lets nobody in, standing in for whatever a feature contributes."""
    raise UnauthorizedException("Not authenticated")


async def _admit() -> dict[str, int]:
    """The same guard, for a caller it accepts."""
    return {"id": 1}


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
    """The app's settings; the lifespan reads only the database ones itself."""
    return settings.model_copy()


@pytest.fixture
def feature_lifecycles():
    """Two stand-in features, recording the order their startups and shutdowns run in.

    The lifespan knows nothing about which features a project selected, so these
    are ordinary ``Lifecycle`` values rather than patched module globals.
    """
    call_order: list[str] = []

    def recorder(name: str) -> AsyncMock:
        return AsyncMock(side_effect=lambda *args, **kwargs: call_order.append(name))

    first = Lifecycle(
        "first",
        startup=recorder("first_startup"),
        shutdown=(recorder("first_shutdown"), recorder("first_client_close")),
    )
    second = Lifecycle("second", startup=recorder("second_startup"), shutdown=(recorder("second_shutdown"),))

    return (first, second), call_order


@pytest.fixture
def database_calls():
    """The database steps the core itself owns."""
    mocks = {"create_tables": AsyncMock(), "close_database": AsyncMock()}

    with ExitStack() as stack:
        for name, mock in mocks.items():
            stack.enter_context(patch(f"src.infrastructure.app_factory.{name}", mock))
        yield mocks


class TestLifespanDatabaseTeardown:
    """The lifespan must drain the connection pool on the way out."""

    async def test_disposes_engine_on_clean_shutdown(self, lifespan_settings, database_calls, feature_lifecycles):
        """close_database is awaited once after a normal shutdown."""
        lifecycles, _ = feature_lifecycles
        lifespan = app_factory.lifespan_factory(lifespan_settings, lifecycles=lifecycles)

        async with lifespan(FastAPI()):
            database_calls["close_database"].assert_not_awaited()

        database_calls["close_database"].assert_awaited_once()

    async def test_teardown_runs_in_reverse_order_with_database_last(
        self, lifespan_settings, database_calls, feature_lifecycles
    ):
        """Features start in wiring order and are torn down in reverse, the database last."""
        lifecycles, call_order = feature_lifecycles
        lifespan = app_factory.lifespan_factory(lifespan_settings, lifecycles=lifecycles)

        async with lifespan(FastAPI()):
            assert call_order == ["first_startup", "second_startup"]

        assert call_order == [
            "first_startup",
            "second_startup",
            "second_shutdown",
            "first_shutdown",
            "first_client_close",
        ]
        database_calls["close_database"].assert_awaited_once()

    async def test_disposes_when_body_raises(self, lifespan_settings, database_calls, feature_lifecycles):
        """A failure while the app is serving still drains the pool."""
        lifecycles, _ = feature_lifecycles
        lifespan = app_factory.lifespan_factory(lifespan_settings, lifecycles=lifecycles)

        with pytest.raises(RuntimeError, match="boom"):
            async with lifespan(FastAPI()):
                raise RuntimeError("boom")

        database_calls["close_database"].assert_awaited_once()

    async def test_disposes_when_startup_fails(self, lifespan_settings, database_calls, feature_lifecycles):
        """A failure partway through startup still drains the pool, and unwinds what started."""
        lifecycles, call_order = feature_lifecycles
        lifecycles[1].startup.side_effect = RuntimeError("cache down")
        lifespan = app_factory.lifespan_factory(lifespan_settings, lifecycles=lifecycles)

        with pytest.raises(RuntimeError, match="cache down"):
            async with lifespan(FastAPI()):
                pytest.fail("startup should not have completed")

        assert call_order == ["first_startup", "second_shutdown", "first_shutdown", "first_client_close"]
        database_calls["close_database"].assert_awaited_once()

    async def test_skips_dispose_without_database_settings(self, database_calls, feature_lifecycles):
        """Settings that carry no database config leave the engine alone."""
        lifecycles, _ = feature_lifecycles
        lifespan = app_factory.lifespan_factory(object(), lifecycles=lifecycles)  # type: ignore[arg-type]

        async with lifespan(FastAPI()):
            pass

        database_calls["close_database"].assert_not_awaited()
        database_calls["create_tables"].assert_not_awaited()


def _create_app(
    environment: EnvironmentOption,
    enable_docs_in_production: bool = False,
    docs_guard: Callable[..., Any] | None = _refuse,
) -> FastAPI:
    return app_factory.create_application(
        router=APIRouter(),
        settings=Settings(ENVIRONMENT=environment, ENABLE_DOCS_IN_PRODUCTION=enable_docs_in_production),
        docs_guard=docs_guard,
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
async def test_gated_docs_are_served_to_whoever_the_guard_admits(environment, enable_docs_in_production):
    app = _create_app(environment, enable_docs_in_production, docs_guard=_admit)

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
    app = app_factory.create_application(router=APIRouter(), settings=custom, docs_guard=_refuse)

    assert await _statuses(app, custom_paths) == [401, 401, 401]
    assert await _docs_statuses(app) == [404, 404, 404]

    admitting = app_factory.create_application(router=APIRouter(), settings=custom, docs_guard=_admit)

    assert await _statuses(admitting, custom_paths) == [200, 200, 200]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("environment", "enable_docs_in_production"),
    [(EnvironmentOption.STAGING, False), (EnvironmentOption.PRODUCTION, True)],
)
async def test_docs_are_hidden_when_no_feature_can_guard_them(environment, enable_docs_in_production):
    """Without a guard there is nobody to let in, so the docs are not served at all.

    A project that selected no accounts feature contributes no ``DOCS_GUARD``, and
    unguarded docs outside development would be public.
    """
    app = _create_app(environment, enable_docs_in_production, docs_guard=None)

    assert await _docs_statuses(app) == [404, 404, 404]


@pytest.mark.asyncio
async def test_no_configured_origin_means_no_cross_origin_allowance():
    """An empty allowlist must not become a wildcard."""
    app = app_factory.create_application(router=APIRouter(), settings=Settings(CORS_ORIGINS=""))

    assert not [middleware for middleware in app.user_middleware if middleware.cls is CORSMiddleware]


@pytest.mark.asyncio
async def test_a_wildcard_origin_never_carries_credentials():
    """Starlette would otherwise echo any Origin back together with the cookie."""
    app = app_factory.create_application(router=APIRouter(), settings=Settings(CORS_ORIGINS="*", CORS_ALLOW_CREDENTIALS=True))

    cors = next(middleware for middleware in app.user_middleware if middleware.cls is CORSMiddleware)

    assert cors.kwargs["allow_origins"] == ["*"]
    assert cors.kwargs["allow_credentials"] is False


@pytest.mark.asyncio
async def test_named_origins_still_carry_credentials():
    app = app_factory.create_application(
        router=APIRouter(), settings=Settings(CORS_ORIGINS="https://app.example.com", CORS_ALLOW_CREDENTIALS=True)
    )

    cors = next(middleware for middleware in app.user_middleware if middleware.cls is CORSMiddleware)

    assert cors.kwargs["allow_origins"] == ["https://app.example.com"]
    assert cors.kwargs["allow_credentials"] is True


@pytest.mark.asyncio
async def test_an_app_can_be_built_with_wiring_of_its_own():
    """The factory builds whatever project it is handed, not the one it was compiled with."""
    installed: list[str] = []
    extra = APIRouter()

    @extra.get("/from-the-wiring")
    async def from_the_wiring() -> dict[str, bool]:
        return {"mounted": True}

    app = app_factory.create_application(
        router=APIRouter(),
        settings=Settings(ENVIRONMENT=EnvironmentOption.LOCAL),
        root_routers=(extra,),
        installers=(lambda application: installed.append("installed"),),
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/from-the-wiring")

    assert response.status_code == 200
    assert installed == ["installed"]


@pytest.mark.asyncio
async def test_the_api_metadata_settings_reach_the_schema():
    """They used to be overridden by literals the app passed in, so nobody could set them."""
    app = app_factory.create_application(
        router=APIRouter(),
        settings=Settings(API_TITLE="Acme API", API_VERSION="2.5.0", API_DESCRIPTION="What Acme runs on"),
    )

    info = app.openapi()["info"]

    assert info["title"] == "Acme API"
    assert info["version"] == "2.5.0"
    assert info["description"] == "What Acme runs on"
