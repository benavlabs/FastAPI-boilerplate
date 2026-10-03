"""Unit tests for the application factory."""

import json
import os
import subprocess
import sys
from collections.abc import Callable
from contextlib import ExitStack
from pathlib import Path
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
from src.infrastructure.middleware import ClientCacheMiddleware

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

    async def test_the_factorys_own_lifespan_starts_the_lifecycles_it_is_given(self, database_calls, feature_lifecycles):
        """An app built without a custom lifespan still starts the features it was wired with."""
        lifecycles, call_order = feature_lifecycles
        app = app_factory.create_application(
            router=APIRouter(),
            settings=Settings(),
            lifecycles=lifecycles,
            create_tables_on_startup=False,
        )

        async with app.router.lifespan_context(app):
            assert call_order == ["first_startup", "second_startup"]

        assert call_order == [
            "first_startup",
            "second_startup",
            "second_shutdown",
            "first_shutdown",
            "first_client_close",
        ]


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


def test_the_cache_middleware_is_told_the_configured_api_prefix():
    """It decides the no-store wording from the prefix, which it can only get from here."""
    app = app_factory.create_application(router=APIRouter(), settings=Settings(API_PREFIX="/service"))

    cache = next(middleware for middleware in app.user_middleware if middleware.cls is ClientCacheMiddleware)

    assert cache.kwargs["api_prefix"] == "/service"


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
async def test_the_api_metadata_settings_reach_the_schema(monkeypatch):
    """They used to be overridden by literals the app passed in, so nobody could set them."""
    monkeypatch.setenv("API_TITLE", "Acme API")
    monkeypatch.setenv("API_VERSION", "2.5.0")
    monkeypatch.setenv("API_DESCRIPTION", "What Acme runs on")

    app = app_factory.create_application(router=APIRouter(), settings=Settings())

    info = app.openapi()["info"]

    assert info["title"] == "Acme API"
    assert info["version"] == "2.5.0"
    assert info["description"] == "What Acme runs on"


METADATA_VARIABLES = (
    "API_TITLE",
    "API_SUMMARY",
    "API_DESCRIPTION",
    "API_VERSION",
    "API_TERMS_OF_SERVICE",
    "API_CONTACT_NAME",
    "API_CONTACT_EMAIL",
    "API_CONTACT_URL",
    "API_LICENSE_NAME",
    "API_LICENSE_URL",
    "API_LICENSE_IDENTIFIER",
    "API_TAGS_METADATA",
    "APP_DESCRIPTION",
    "VERSION",
)

_PROJECT_INFO = """
import json
import sys

from fastapi import APIRouter

from src.infrastructure import app_factory
from src.infrastructure.config.settings import Settings

application = app_factory.create_application(router=APIRouter(), settings=Settings(**json.loads(sys.argv[1])))

print("INFO:" + json.dumps(application.openapi()["info"]))
"""


def _project_info(environment: dict[str, str] | None = None, **overrides: str) -> dict[str, Any]:
    """The ``info`` block of a project configured by ``environment`` and ``overrides`` alone.

    The settings read their defaults from the environment when the config module is
    imported, so a project that configured nothing is only visible from a cold
    interpreter that was started without those variables.
    """
    child = {name: value for name, value in os.environ.items() if name not in METADATA_VARIABLES}
    child.update(environment or {})

    result = subprocess.run(
        [sys.executable, "-c", _PROJECT_INFO, json.dumps(overrides)],
        cwd=Path(__file__).resolve().parents[3],
        capture_output=True,
        text=True,
        check=True,
        env=child,
    )
    line = next(line for line in result.stdout.splitlines() if line.startswith("INFO:"))

    info: dict[str, Any] = json.loads(line.removeprefix("INFO:"))

    return info


class TestTheProjectsIdentity:
    """A generated project must not inherit the template's identity, or an invalid licence."""

    def test_nothing_configured_means_no_contact_and_no_licence(self):
        info = _project_info()

        assert "contact" not in info
        assert "license" not in info
        assert "summary" not in info

    def test_nothing_configured_means_no_version_or_description_of_the_template(self):
        """The defaults used to ship the boilerplate's own version and its README heading."""
        info = _project_info()

        assert info["version"] == "0.1.0"
        assert "description" not in info

    def test_a_licence_needs_a_name(self):
        """OpenAPI requires the name; an identifier alone is not a licence."""
        assert "license" not in _project_info(API_LICENSE_IDENTIFIER="MIT")

    def test_a_licence_carries_an_identifier_or_a_url_but_not_both(self):
        """OpenAPI allows one of them, and the identifier is the one it prefers."""
        both = _project_info(API_LICENSE_NAME="MIT", API_LICENSE_IDENTIFIER="MIT", API_LICENSE_URL="https://example.com/l")

        assert both["license"] == {"name": "MIT", "identifier": "MIT"}
        assert _project_info(API_LICENSE_NAME="MIT", API_LICENSE_URL="https://example.com/l")["license"] == {
            "name": "MIT",
            "url": "https://example.com/l",
        }

    def test_the_contact_is_whatever_the_project_configured(self):
        info = _project_info(API_CONTACT_NAME="Acme Support", API_CONTACT_EMAIL="ops@acme.example.com")

        assert info["contact"] == {"name": "Acme Support", "email": "ops@acme.example.com"}

    def test_a_legacy_contact_in_the_environment_reaches_nothing(self):
        """``CONTACT_NAME`` and friends are gone; a stale .env must not name a contact."""
        info = _project_info(
            environment={
                "CONTACT_NAME": "Template Author",
                "CONTACT_EMAIL": "author@template.example.com",
                "LICENSE_NAME": "MIT",
            }
        )

        assert "contact" not in info
        assert "license" not in info


@pytest.mark.asyncio
async def test_the_gated_docs_follow_the_mount_the_request_arrived_through():
    """Behind ``--root-path`` the gated pages pointed at a schema URL that answers 404."""
    guarded = app_factory.create_application(
        router=APIRouter(), settings=Settings(ENVIRONMENT=EnvironmentOption.STAGING), docs_guard=_admit
    )
    builtin = app_factory.create_application(router=APIRouter(), settings=Settings(ENVIRONMENT=EnvironmentOption.LOCAL))

    async with AsyncClient(transport=ASGITransport(app=guarded, root_path="/svc"), base_url="http://test") as client:
        docs = await client.get("/svc/docs")
        redoc = await client.get("/svc/redoc")
        gated_schema = (await client.get("/svc/openapi.json")).json()

    async with AsyncClient(transport=ASGITransport(app=builtin, root_path="/svc"), base_url="http://test") as client:
        builtin_schema = (await client.get("/svc/openapi.json")).json()

    assert "/svc/openapi.json" in docs.text
    assert "/svc/openapi.json" in redoc.text
    assert gated_schema["servers"] == [{"url": "/svc"}]
    assert gated_schema == builtin_schema


@pytest.mark.asyncio
async def test_the_gated_schema_is_the_one_the_app_builds():
    """It was rebuilt from title, version and description, so the rest never reached a reader."""
    configured = Settings(
        ENVIRONMENT=EnvironmentOption.STAGING,
        API_SUMMARY="What Acme runs on",
        API_TERMS_OF_SERVICE="https://acme.example.com/terms",
        API_CONTACT_NAME="Acme Support",
        API_CONTACT_EMAIL="ops@acme.example.com",
        API_LICENSE_NAME="MIT",
        API_TAGS_METADATA='[{"name": "users", "description": "Accounts"}]',
    )
    app = app_factory.create_application(router=APIRouter(), settings=configured, docs_guard=_admit)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        served = (await client.get("/openapi.json")).json()

    assert served == app.openapi()
    assert served["info"]["summary"] == "What Acme runs on"
    assert served["info"]["termsOfService"] == "https://acme.example.com/terms"
    assert served["info"]["contact"] == {"name": "Acme Support", "email": "ops@acme.example.com"}
    assert served["info"]["license"] == {"name": "MIT"}
    assert served["tags"] == [{"name": "users", "description": "Accounts"}]
