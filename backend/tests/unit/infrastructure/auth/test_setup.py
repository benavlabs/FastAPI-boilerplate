"""Tests for the crudauth composition root wiring."""

import os
import subprocess
import sys
from pathlib import Path

from crudauth import NewUserContext
from starlette.requests import Request

from src.infrastructure.auth import setup
from src.infrastructure.config.settings import settings
from src.modules.user.constants import NAME_MAX_LENGTH

_OAUTH_ROUTES = """
from src.infrastructure.auth.routes import root_routers
from src.infrastructure.auth.setup import OAUTH_PREFIX

print("PREFIX:" + OAUTH_PREFIX)
print("PATHS:" + ",".join(route.path for router in root_routers for route in router.routes))
"""


def _oauth_routes(**environment: str) -> tuple[str, list[str]]:
    """The OAuth prefix and the paths its router serves, read from a cold interpreter."""
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
    """Only a fully configured Google is wired; the boilerplate has no other provider route."""

    def test_google_is_wired_when_both_credentials_are_set(self, monkeypatch):
        monkeypatch.setattr(settings, "OAUTH_GOOGLE_CLIENT_ID", "client-id")
        monkeypatch.setattr(settings, "OAUTH_GOOGLE_CLIENT_SECRET", "client-secret")

        providers = setup._oauth_providers()

        assert set(providers) == {"google"}
        assert providers["google"].client_id == "client-id"

    def test_google_is_dropped_when_a_credential_is_missing(self, monkeypatch):
        monkeypatch.setattr(settings, "OAUTH_GOOGLE_CLIENT_ID", "client-id")
        monkeypatch.setattr(settings, "OAUTH_GOOGLE_CLIENT_SECRET", "")

        assert setup._oauth_providers() == {}

    def test_github_credentials_do_not_add_an_unrouted_provider(self, monkeypatch):
        monkeypatch.setattr(settings, "OAUTH_GOOGLE_CLIENT_ID", "")
        monkeypatch.setattr(settings, "OAUTH_GOOGLE_CLIENT_SECRET", "")
        monkeypatch.setattr(settings, "OAUTH_GITHUB_CLIENT_ID", "gh-id")
        monkeypatch.setattr(settings, "OAUTH_GITHUB_CLIENT_SECRET", "gh-secret")

        assert setup._oauth_providers() == {}


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
