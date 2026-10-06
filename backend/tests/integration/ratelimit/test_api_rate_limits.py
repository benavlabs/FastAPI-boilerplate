"""Per-path rate limits on the API routes, through crudauth's limiter.

The paths come from the app itself, so a project throttles whichever routes its
features contributed rather than a list that has to be kept in step.
"""

import itertools

import pytest
from fastapi.routing import APIRoute
from httpx import AsyncClient

from src.infrastructure.config.settings import settings
from src.infrastructure.ratelimit.dependency import api_rate_limit_dependency
from src.interfaces.main import app

pytestmark = pytest.mark.asyncio

_addresses = (f"198.51.100.{n}" for n in itertools.count(1))

THROTTLED_READS = sorted(
    {
        route.path
        for route in app.routes
        if isinstance(route, APIRoute)
        and "GET" in route.methods
        and route.path.endswith("/")
        and any(dependency.call is api_rate_limit_dependency for dependency in route.dependant.dependencies)
    }
)


@pytest.fixture
def limits(monkeypatch):
    """A small default limit, and each test's anonymous caller on its own address."""
    monkeypatch.setattr(settings, "RATE_LIMITER_ENABLED", True)
    monkeypatch.setattr(settings, "DEFAULT_RATE_LIMIT_LIMIT", 3)
    monkeypatch.setattr(settings, "DEFAULT_RATE_LIMIT_PERIOD", 3600)
    monkeypatch.setattr(settings, "TRUSTED_PROXY_HOPS", 1)
    return {"X-Forwarded-For": next(_addresses)}


async def test_the_default_limit_is_enforced(client: AsyncClient, limits: dict):
    statuses = [(await client.get(THROTTLED_READS[0], headers=limits)).status_code for _ in range(4)]

    assert statuses[:3] == [401, 401, 401]
    assert statuses[3] == 429


async def test_a_refused_request_still_reports_the_budget_it_spent(client: AsyncClient, limits: dict):
    """A 401 after the limiter counted the request tells the client what it has left."""
    responses = [await client.get(THROTTLED_READS[0], headers=limits) for _ in range(4)]

    assert [response.status_code for response in responses] == [401, 401, 401, 429]
    assert [response.headers.get("X-RateLimit-Remaining") for response in responses] == ["2", "1", "0", "0"]
    assert all(response.headers.get("X-RateLimit-Limit") == "3" for response in responses)


@pytest.mark.skipif(len(THROTTLED_READS) < 2, reason="needs two throttled routes to compare budgets")
async def test_each_path_keeps_its_own_budget(client: AsyncClient, limits: dict):
    """Spending the budget on one route never throttles another."""
    for _ in range(3):
        await client.get(THROTTLED_READS[0], headers=limits)

    exhausted = await client.get(THROTTLED_READS[0], headers=limits)
    other_path = [(await client.get(THROTTLED_READS[1], headers=limits)).status_code for _ in range(4)]

    assert exhausted.status_code == 429
    assert other_path[:3] == [401, 401, 401]
    assert other_path[3] == 429


async def test_disabling_rate_limits_lets_every_request_through(client: AsyncClient, limits: dict, monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMITER_ENABLED", False)

    statuses = [(await client.get(THROTTLED_READS[0], headers=limits)).status_code for _ in range(5)]

    assert 429 not in statuses


async def test_a_path_parameter_does_not_hand_out_a_fresh_budget(client: AsyncClient, limits: dict):
    """Every value of a path parameter is the same route, so they share one allowance."""
    responses = [(await client.get(f"/api/v1/users/{name}", headers=limits)).status_code for name in "abcd"]

    assert responses[3] == 429


@pytest.fixture
def throttled(monkeypatch):
    """The API throttle on, with a limit no test is meant to reach."""
    monkeypatch.setattr(settings, "RATE_LIMITER_ENABLED", True)
    monkeypatch.setattr(settings, "DEFAULT_RATE_LIMIT_LIMIT", 100)
    monkeypatch.setattr(settings, "DEFAULT_RATE_LIMIT_PERIOD", 3600)


@pytest.mark.usefixtures("fresh_login_lockout")
class TestTheHeadersOnAPasswordChange:
    """The change-password route carries the budget's headers on every response."""

    async def test_a_wrong_password_reports_the_budget(self, client: AsyncClient, test_user: dict, throttled: None):
        login = await client.post(
            "/api/v1/auth/login",
            data={"username": test_user["username"], "password": test_user["password"]},
        )
        assert login.status_code == 200

        refused = await client.post(
            "/api/v1/auth/change-password",
            json={"current_password": "WrongPassword1!", "new_password": "An0therPassword!"},
            headers={"X-CSRF-Token": login.json()["csrf_token"]},
        )

        assert refused.status_code == 401
        assert refused.headers["X-RateLimit-Limit"] == "5"
        assert refused.headers["X-RateLimit-Remaining"] == "4"
