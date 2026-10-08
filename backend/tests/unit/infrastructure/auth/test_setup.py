"""Tests for the crudauth composition root wiring."""

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from crudauth import NewUserContext
from starlette.requests import Request

from src.infrastructure.auth import setup
from src.infrastructure.config.settings import settings
from src.modules.user.constants import NAME_MAX_LENGTH

LOCKOUT_SETTINGS = (
    "LOGIN_MAX_ATTEMPTS",
    "LOGIN_ATTEMPT_WINDOW_SECONDS",
    "LOGIN_LOCKOUT_BASE_SECONDS",
    "LOGIN_LOCKOUT_MAX_SECONDS",
)

_LOCKOUT_DEFAULTS = """
import json
import sys

from src.infrastructure.auth.settings import AuthSettings

names = json.loads(sys.argv[1])

print("DEFAULTS:" + json.dumps({name: AuthSettings.model_fields[name].default for name in names}))
"""


def _lockout_defaults() -> dict[str, int]:
    """The declared defaults, from an interpreter whose environment sets none of them.

    The settings read their defaults from the environment when the module is imported, so
    an exported ``LOGIN_*`` is indistinguishable from a declared default in this process.
    """
    child = {name: value for name, value in os.environ.items() if name not in LOCKOUT_SETTINGS}
    result = subprocess.run(
        [sys.executable, "-c", _LOCKOUT_DEFAULTS, json.dumps(LOCKOUT_SETTINGS)],
        cwd=Path(__file__).resolve().parents[4],
        capture_output=True,
        text=True,
        check=True,
        env=child,
    )
    line = next(line for line in result.stdout.splitlines() if line.startswith("DEFAULTS:"))

    defaults: dict[str, int] = json.loads(line.removeprefix("DEFAULTS:"))

    return defaults


_OAUTH_ROUTES = """
from src.infrastructure.auth.routes import root_routers
from src.infrastructure.auth.setup import OAUTH_PREFIX

print("PREFIX:" + OAUTH_PREFIX)
print("PATHS:" + ",".join(route.path for router in root_routers for route in router.routes))
"""


def _oauth_routes(**environment: str) -> tuple[str, list[str]]:
    """The OAuth prefix and the paths its router serves, read from a cold interpreter.

    Every provider's credentials are passed explicitly, so what the developer's own
    environment holds cannot decide which routes the child mounts.
    """
    result = subprocess.run(
        [sys.executable, "-c", _OAUTH_ROUTES],
        cwd=Path(__file__).resolve().parents[4],
        capture_output=True,
        text=True,
        check=True,
        env={
            **os.environ,
            "OAUTH_GOOGLE_CLIENT_ID": "client-id",
            "OAUTH_GOOGLE_CLIENT_SECRET": "client-secret",
            "OAUTH_GITHUB_CLIENT_ID": "",
            "OAUTH_GITHUB_CLIENT_SECRET": "",
            **environment,
        },
    )
    output = {line.split(":", 1)[0]: line.split(":", 1)[1] for line in result.stdout.splitlines() if ":" in line}

    return output["PREFIX"], [path for path in output["PATHS"].split(",") if path]


def _request(path: str, client_host: str = "203.0.113.7") -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": path,
            "raw_path": path.encode(),
            "query_string": b"",
            "headers": [],
            "client": (client_host, 1234),
            "server": ("test", 80),
            "scheme": "http",
        }
    )


class TestSessionRedisWiring:
    """Session storage uses SESSION_REDIS_URL, on a different DB than the cache by default."""

    def test_sessions_get_a_redis_database_of_their_own(self):
        """Another service's FLUSHDB must not reach the database holding sessions."""
        other_dbs = {
            getattr(settings, name)
            for name in ("CACHE_REDIS_DB", "RATE_LIMITER_REDIS_DB", "TASKIQ_REDIS_DB")
            if hasattr(settings, name)
        }

        assert settings.SESSION_REDIS_DB not in other_dbs
        assert settings.SESSION_REDIS_URL.endswith(f"/{settings.SESSION_REDIS_DB}")

    def test_redis_sessions_are_built_from_the_session_url(self, monkeypatch):
        monkeypatch.setattr(settings, "SESSION_BACKEND", "redis")

        transport = setup._session_transport()

        assert transport.redis_url == settings.SESSION_REDIS_URL

    def test_memory_sessions_carry_no_redis_url(self, monkeypatch):
        monkeypatch.setattr(settings, "SESSION_BACKEND", "memory")
        monkeypatch.setattr(settings, "RATE_LIMITER_BACKEND", "redis")

        assert setup._session_transport().redis_url is None


class TestOAuthWiring:
    """The callback URI crudauth sends to the provider matches the route that serves it."""

    def test_the_callback_lives_under_the_api_prefix(self):
        assert setup.OAUTH_PREFIX == "/api/v1/auth/oauth"

    def test_a_configured_api_prefix_moves_the_oauth_routes(self):
        """The prefix was written out here, so a moved API served its OAuth routes nowhere."""
        prefix, paths = _oauth_routes(API_PREFIX="/service")

        assert prefix == "/service/v1/auth/oauth"
        assert paths
        assert [path for path in paths if not path.startswith("/service/v1/auth/oauth")] == []


class TestOAuthProviderSelection:
    """A provider is wired when both of its credentials are set, and only then."""

    @pytest.fixture
    def credentials(self, monkeypatch):
        """The four OAuth settings, as a project's environment would leave them."""

        def configured(**values: str) -> dict[str, Any]:
            for provider in ("GOOGLE", "GITHUB"):
                for part in ("CLIENT_ID", "CLIENT_SECRET"):
                    name = f"OAUTH_{provider}_{part}"
                    monkeypatch.setattr(settings, name, values.get(name, ""))

            return setup._oauth_providers()

        return configured

    def test_google_alone_is_wired_from_its_own_credentials(self, credentials):
        providers = credentials(OAUTH_GOOGLE_CLIENT_ID="google-id", OAUTH_GOOGLE_CLIENT_SECRET="google-secret")

        assert set(providers) == {"google"}
        assert (providers["google"].client_id, providers["google"].client_secret) == ("google-id", "google-secret")

    def test_github_alone_is_wired_from_its_own_credentials(self, credentials):
        providers = credentials(OAUTH_GITHUB_CLIENT_ID="github-id", OAUTH_GITHUB_CLIENT_SECRET="github-secret")

        assert set(providers) == {"github"}
        assert (providers["github"].client_id, providers["github"].client_secret) == ("github-id", "github-secret")

    def test_both_are_wired_together(self, credentials):
        providers = credentials(
            OAUTH_GOOGLE_CLIENT_ID="google-id",
            OAUTH_GOOGLE_CLIENT_SECRET="google-secret",
            OAUTH_GITHUB_CLIENT_ID="github-id",
            OAUTH_GITHUB_CLIENT_SECRET="github-secret",
        )

        assert set(providers) == {"google", "github"}

    @pytest.mark.parametrize(
        "configured",
        [
            {"OAUTH_GOOGLE_CLIENT_ID": "google-id"},
            {"OAUTH_GOOGLE_CLIENT_SECRET": "google-secret"},
            {"OAUTH_GITHUB_CLIENT_ID": "github-id"},
            {"OAUTH_GITHUB_CLIENT_SECRET": "github-secret"},
        ],
    )
    def test_half_a_provider_is_no_provider(self, credentials, configured: dict[str, str]):
        """A client id without its secret cannot complete a sign-in, so the route stays off."""
        assert credentials(**configured) == {}

    def test_a_project_that_configured_none_mounts_no_oauth_router(self):
        prefix, paths = _oauth_routes(OAUTH_GOOGLE_CLIENT_ID="", OAUTH_GOOGLE_CLIENT_SECRET="")

        assert prefix == "/api/v1/auth/oauth"
        assert paths == []

    @pytest.mark.parametrize(
        "configured",
        [
            {"OAUTH_GOOGLE_CLIENT_ID": "google-id", "OAUTH_GOOGLE_CLIENT_SECRET": "google-secret"},
            {"OAUTH_GITHUB_CLIENT_ID": "github-id", "OAUTH_GITHUB_CLIENT_SECRET": "github-secret"},
        ],
    )
    def test_one_configured_provider_mounts_the_oauth_router(self, configured: dict[str, str]):
        _, paths = _oauth_routes(**{"OAUTH_GOOGLE_CLIENT_ID": "", "OAUTH_GOOGLE_CLIENT_SECRET": "", **configured})

        assert paths == ["/api/v1/auth/oauth/{provider}", "/api/v1/auth/oauth/callback/{provider}"]


class TestNewUserFields:
    """crudauth creates the account; the boilerplate supplies the required display name."""

    def test_the_display_name_is_filled_and_bounded(self):
        context = NewUserContext(
            email="a" * (NAME_MAX_LENGTH + 10) + "@example.com",
            username="auser",
            source="register",
            db=None,  # type: ignore[arg-type]
        )

        fields = setup._new_user_fields(context)

        assert fields["name"] == "a" * NAME_MAX_LENGTH
        assert len(fields["name"]) == NAME_MAX_LENGTH


class TestSessionTransportWiring:
    """The session settings reach the transport instead of the library defaults."""

    def test_the_session_settings_reach_the_transport(self, monkeypatch):
        monkeypatch.setattr(settings, "SESSION_BACKEND", "memory")
        monkeypatch.setattr(settings, "CSRF_ENABLED", False)
        monkeypatch.setattr(settings, "MAX_SESSIONS_PER_USER", 2)
        monkeypatch.setattr(settings, "SESSION_TIMEOUT_MINUTES", 7)
        monkeypatch.setattr(settings, "SESSION_CLEANUP_INTERVAL_MINUTES", 3)

        transport = setup._session_transport()

        assert transport.csrf_enabled is False
        assert transport.max_sessions_per_user == 2
        assert transport.session_timeout_minutes == 7
        assert transport.cleanup_interval_minutes == 3

    @pytest.mark.parametrize("backend", ["redis", "memory", "database"])
    def test_the_session_backend_setting_names_the_store(self, monkeypatch, backend: str):
        monkeypatch.setattr(settings, "SESSION_BACKEND", backend)

        transport = setup._session_transport()

        assert transport.backend == backend
        assert (transport.redis_url is not None) is (backend == "redis")

    def test_a_backend_crudauth_has_no_store_for_is_refused(self, monkeypatch):
        monkeypatch.setattr(settings, "SESSION_BACKEND", "memcached")

        with pytest.raises(ValueError, match="SESSION_BACKEND"):
            setup._session_transport()

    def test_no_absolute_cap_is_configured_by_default(self):
        """A session ends on the idle timeout alone unless a project asks for a cap."""
        assert settings.SESSION_ABSOLUTE_TIMEOUT_HOURS is None
        assert setup._session_transport().absolute_timeout_hours is None

    def test_the_absolute_cap_reaches_the_transport(self, monkeypatch):
        monkeypatch.setattr(settings, "SESSION_ABSOLUTE_TIMEOUT_HOURS", 12)

        assert setup._session_transport().absolute_timeout_hours == 12

    @pytest.mark.parametrize("hours", [0, -1])
    def test_a_cap_below_an_hour_is_refused(self, monkeypatch, hours: int):
        """The library would take it and expire every session as soon as it was created."""
        monkeypatch.setattr(settings, "SESSION_ABSOLUTE_TIMEOUT_HOURS", hours)

        with pytest.raises(ValueError, match="SESSION_ABSOLUTE_TIMEOUT_HOURS"):
            setup._session_transport()


class TestAccountsLifecycle:
    """What the app runs for accounts on startup and shutdown."""

    def test_starts_crudauth_and_closes_what_it_opened(self):
        assert setup.lifecycle.name == "accounts"
        assert setup.lifecycle.startup == setup.auth.initialize
        assert setup.auth.shutdown in setup.lifecycle.shutdown

    async def test_the_limiter_client_closes_whatever_else_is_wired(self, monkeypatch):
        """The login lockout uses the client whether or not API routes are throttled."""
        closed = False

        async def record_close() -> None:
            nonlocal closed
            closed = True

        monkeypatch.setattr(setup.rate_limiter_redis_client, "aclose", record_close)

        for shutdown in setup.lifecycle.shutdown:
            if shutdown is not setup.auth.shutdown:
                await shutdown()

        assert closed


class TestTheLoginLockout:
    """The policy crudauth runs the login on carries this project's four settings."""

    def test_the_thresholds_the_project_configured_reach_the_policy(self):
        lockout = setup.auth.runtime.lockout

        assert lockout is not None
        assert lockout.max_attempts == settings.LOGIN_MAX_ATTEMPTS
        assert lockout.attempt_window == settings.LOGIN_ATTEMPT_WINDOW_SECONDS
        assert lockout.lockout_base == settings.LOGIN_LOCKOUT_BASE_SECONDS
        assert lockout.lockout_max == settings.LOGIN_LOCKOUT_MAX_SECONDS

    def test_the_declared_defaults_count_over_fifteen_minutes(self):
        """The defaults a project gets, read from an interpreter started without the variables."""
        assert _lockout_defaults() == {
            "LOGIN_MAX_ATTEMPTS": 5,
            "LOGIN_ATTEMPT_WINDOW_SECONDS": 900,
            "LOGIN_LOCKOUT_BASE_SECONDS": 300,
            "LOGIN_LOCKOUT_MAX_SECONDS": 3600,
        }
