"""Tests for the crudauth composition root wiring."""

from types import SimpleNamespace

import pytest
from crudauth import NewUserContext, Principal
from starlette.requests import Request

from src.infrastructure.auth import setup
from src.infrastructure.config.settings import settings
from src.infrastructure.database.session import async_session
from src.infrastructure.redis import rate_limiter_redis_client
from src.modules.rate_limit.crud import crud_rate_limits
from src.modules.user.constants import NAME_MAX_LENGTH


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

    def test_session_redis_db_is_not_the_cache_db(self):
        """By default a cache FLUSHDB must not reach the database holding sessions."""
        assert settings.SESSION_REDIS_DB != settings.CACHE_REDIS_DB
        assert settings.SESSION_REDIS_URL.endswith(f"/{settings.SESSION_REDIS_DB}")

    def test_redis_sessions_are_built_from_the_session_url(self, monkeypatch):
        monkeypatch.setattr(settings, "SESSION_BACKEND", "redis")

        transport = setup._session_transport()

        assert transport.redis_url == settings.SESSION_REDIS_URL

    def test_memory_sessions_carry_no_redis_url(self, monkeypatch):
        monkeypatch.setattr(settings, "SESSION_BACKEND", "memory")
        monkeypatch.setattr(settings, "RATE_LIMITER_BACKEND", "redis")

        assert setup._session_transport().redis_url is None


class TestRateLimiterBackend:
    """RATE_LIMITER_BACKEND alone decides where the limiter and login lockout count."""

    def test_redis_uses_the_shared_limiter_client(self, monkeypatch):
        monkeypatch.setattr(settings, "RATE_LIMITER_BACKEND", "redis")
        monkeypatch.setattr(settings, "SESSION_BACKEND", "memory")

        backend = setup._rate_limiter()

        assert backend is not None
        assert backend.client is rate_limiter_redis_client

    def test_memory_leaves_crudauth_its_in_process_limiter(self, monkeypatch):
        monkeypatch.setattr(settings, "RATE_LIMITER_BACKEND", "memory")

        assert setup._rate_limiter() is None

    def test_the_removed_memcached_backend_fails_loudly(self, monkeypatch):
        """A deployment still configured for memcached must not silently fall back to memory."""
        monkeypatch.setattr(settings, "RATE_LIMITER_BACKEND", "memcached")

        with pytest.raises(ValueError, match="memcached"):
            setup._rate_limiter()


class TestApiRateLimitKey:
    """Each caller gets one budget per path, so one route can't exhaust another's."""

    def test_signed_in_callers_are_keyed_by_user_and_path(self):
        principal = Principal(user_id=42, transport="session")

        assert setup.api_rate_limit_key(_request("/api/v1/tiers/"), principal) == "user:42:/api/v1/tiers/"

    def test_anonymous_callers_are_keyed_by_ip_and_path(self):
        assert setup.api_rate_limit_key(_request("/api/v1/tiers/"), None) == "ip:203.0.113.7:/api/v1/tiers/"

    def test_different_paths_get_different_budgets(self):
        principal = Principal(user_id=42, transport="session")

        assert setup.api_rate_limit_key(_request("/api/v1/tiers/"), principal) != setup.api_rate_limit_key(
            _request("/api/v1/rate-limits/"), principal
        )

    def test_ipv6_callers_are_keyed_by_their_network(self, monkeypatch):
        """Rotating addresses inside one /64 must not mint fresh budgets."""
        monkeypatch.setattr(settings, "TRUSTED_PROXY_HOPS", 0)

        key = setup.api_rate_limit_key(_request("/api/v1/tiers/", "2001:db8:1:2:3:4:5:6"), None)

        assert key == "ip:2001:db8:1:2::/64:/api/v1/tiers/"


class TestOAuthWiring:
    """The callback URI crudauth sends to the provider matches the route that serves it."""

    def test_the_callback_lives_under_the_api_prefix(self):
        assert setup.OAUTH_PREFIX == "/api/v1/auth/oauth"


_SENTINEL_DB = object()


class TestResolveApiRateLimit:
    """The tier row is read through the request's own database dependency."""

    async def test_the_tier_row_comes_from_the_session_override(self, monkeypatch):
        monkeypatch.setattr(settings, "RATE_LIMITER_ENABLED", True)
        entered: list[bool] = []

        async def override_session():
            entered.append(True)
            yield _SENTINEL_DB

        request = SimpleNamespace(
            url=SimpleNamespace(path="/api/v1/tiers/"),
            app=SimpleNamespace(dependency_overrides={async_session: override_session}),
        )
        principal = Principal(user_id=1, user=SimpleNamespace(tier_id=7), transport="session")
        seen: dict[str, object] = {}

        async def fake_get(db, **kwargs):
            seen["db"] = db
            return {"limit": 2, "period": 3600}

        monkeypatch.setattr(crud_rate_limits, "get", fake_get)

        result = await setup.resolve_api_rate_limit(request, principal)

        assert entered == [True]
        assert seen["db"] is _SENTINEL_DB
        assert (result.times, result.seconds) == (2, 3600)

    async def test_a_caller_without_a_tier_gets_the_default_limit(self, monkeypatch):
        monkeypatch.setattr(settings, "RATE_LIMITER_ENABLED", True)
        monkeypatch.setattr(settings, "DEFAULT_RATE_LIMIT_LIMIT", 11)
        monkeypatch.setattr(settings, "DEFAULT_RATE_LIMIT_PERIOD", 99)

        result = await setup.resolve_api_rate_limit(SimpleNamespace(url=None, app=None), None)

        assert (result.times, result.seconds) == (11, 99)

    async def test_a_disabled_limiter_returns_no_limit(self, monkeypatch):
        monkeypatch.setattr(settings, "RATE_LIMITER_ENABLED", False)

        assert await setup.resolve_api_rate_limit(SimpleNamespace(url=None, app=None), None) is None

    async def test_a_tier_without_a_row_for_the_path_gets_the_default_limit(self, monkeypatch):
        monkeypatch.setattr(settings, "RATE_LIMITER_ENABLED", True)
        monkeypatch.setattr(settings, "DEFAULT_RATE_LIMIT_LIMIT", 11)
        monkeypatch.setattr(settings, "DEFAULT_RATE_LIMIT_PERIOD", 99)

        async def override_session():
            yield _SENTINEL_DB

        request = SimpleNamespace(
            url=SimpleNamespace(path="/api/v1/tiers/"),
            app=SimpleNamespace(dependency_overrides={async_session: override_session}),
        )
        principal = Principal(user_id=1, user=SimpleNamespace(tier_id=7), transport="session")

        async def fake_get(db, **kwargs):
            return None

        monkeypatch.setattr(crud_rate_limits, "get", fake_get)

        result = await setup.resolve_api_rate_limit(request, principal)

        assert (result.times, result.seconds) == (11, 99)

    async def test_a_principal_without_a_loaded_user_gets_the_default_limit(self, monkeypatch):
        monkeypatch.setattr(settings, "RATE_LIMITER_ENABLED", True)
        monkeypatch.setattr(settings, "DEFAULT_RATE_LIMIT_LIMIT", 11)
        monkeypatch.setattr(settings, "DEFAULT_RATE_LIMIT_PERIOD", 99)

        principal = Principal(user_id=1, user=None, transport="session")

        result = await setup.resolve_api_rate_limit(SimpleNamespace(url=None, app=None), principal)

        assert (result.times, result.seconds) == (11, 99)


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
