"""The API throttle: how a budget is named, and which limit applies to a request."""

from types import SimpleNamespace
from typing import cast

from crudauth import Principal
from crudauth.ratelimit import RateLimit
from starlette.requests import Request

from src.infrastructure.config.settings import settings
from src.infrastructure.ratelimit import dependency


def _request_without_a_route() -> Request:
    return cast(Request, SimpleNamespace(url=None, app=None))


def _request(path: str, client_host: str = "203.0.113.7") -> Request:
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": path,
            "raw_path": path.encode(),
            "query_string": b"",
            "root_path": "",
            "headers": [],
            "client": (client_host, 1234),
            "server": ("testserver", 80),
        }
    )


class TestApiRateLimitKey:
    """Each caller gets one budget per path, so one route can't exhaust another's."""

    def test_signed_in_callers_are_keyed_by_user_and_path(self):
        principal = Principal(user_id=42, transport="session")

        assert dependency.api_rate_limit_key(_request("/api/v1/tiers/"), principal) == "user:42:/api/v1/tiers/"

    def test_anonymous_callers_are_keyed_by_ip_and_path(self):
        assert dependency.api_rate_limit_key(_request("/api/v1/tiers/"), None) == "ip:203.0.113.7:/api/v1/tiers/"

    def test_different_paths_get_different_budgets(self):
        principal = Principal(user_id=42, transport="session")

        assert dependency.api_rate_limit_key(_request("/api/v1/tiers/"), principal) != dependency.api_rate_limit_key(
            _request("/api/v1/rate-limits/"), principal
        )

    def test_ipv6_callers_are_keyed_by_their_network(self, monkeypatch):
        """Rotating addresses inside one /64 must not mint fresh budgets."""
        monkeypatch.setattr(settings, "TRUSTED_PROXY_HOPS", 0)

        key = dependency.api_rate_limit_key(_request("/api/v1/tiers/", "2001:db8:1:2:3:4:5:6"), None)

        assert key == "ip:2001:db8:1:2::/64:/api/v1/tiers/"


class TestResolveApiRateLimit:
    """Resolvers are asked in order; the default applies when none answers."""

    async def test_a_disabled_limiter_returns_no_limit(self, monkeypatch):
        monkeypatch.setattr(settings, "RATE_LIMITER_ENABLED", False)

        assert await dependency.resolve_api_rate_limit(_request_without_a_route(), None) is None

    async def test_without_a_resolver_the_default_limit_applies(self, monkeypatch):
        """A project with no tier-limits feature throttles everyone the same way."""
        monkeypatch.setattr(settings, "RATE_LIMITER_ENABLED", True)
        monkeypatch.setattr(settings, "DEFAULT_RATE_LIMIT_LIMIT", 11)
        monkeypatch.setattr(settings, "DEFAULT_RATE_LIMIT_PERIOD", 99)
        monkeypatch.setattr(dependency, "RATE_LIMIT_RESOLVERS", ())

        result = await dependency.resolve_api_rate_limit(_request_without_a_route(), None)

        assert result is not None
        assert (result.times, result.seconds) == (11, 99)

    async def test_the_first_resolver_that_answers_wins(self, monkeypatch):
        monkeypatch.setattr(settings, "RATE_LIMITER_ENABLED", True)

        async def silent(request, principal):
            return None

        async def answers(request, principal):
            return RateLimit(2, 3600)

        async def too_late(request, principal):
            raise AssertionError("a later resolver must not be asked")

        monkeypatch.setattr(dependency, "RATE_LIMIT_RESOLVERS", (silent, answers, too_late))

        result = await dependency.resolve_api_rate_limit(_request_without_a_route(), None)

        assert result is not None
        assert (result.times, result.seconds) == (2, 3600)

    async def test_a_resolver_that_declines_falls_through_to_the_default(self, monkeypatch):
        monkeypatch.setattr(settings, "RATE_LIMITER_ENABLED", True)
        monkeypatch.setattr(settings, "DEFAULT_RATE_LIMIT_LIMIT", 11)
        monkeypatch.setattr(settings, "DEFAULT_RATE_LIMIT_PERIOD", 99)

        async def silent(request, principal):
            return None

        monkeypatch.setattr(dependency, "RATE_LIMIT_RESOLVERS", (silent,))

        result = await dependency.resolve_api_rate_limit(_request_without_a_route(), None)

        assert result is not None
        assert (result.times, result.seconds) == (11, 99)
