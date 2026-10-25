"""A junk ``X-API-Key`` against the API throttle, which needs api_keys and ratelimit.

The transport answers 401 for a key it cannot use, and the throttle counts that refusal
against the address rather than letting it through unmetered.
"""

import itertools

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.config.settings import settings
from src.modules.api_keys.transport import API_KEY_HEADER
from tests.integration.api.v1.api_keys.test_effective_permissions import key_for, with_key

pytestmark = pytest.mark.asyncio

THROTTLED_READ = "/api/v1/users/me"
JUNK_KEY = {API_KEY_HEADER: "fai_xxxxxxxx_junk"}

_addresses = (f"198.51.100.{n}" for n in itertools.count(150))


@pytest.fixture
def limits(monkeypatch):
    """A small default limit, and each test's caller on its own address."""
    monkeypatch.setattr(settings, "RATE_LIMITER_ENABLED", True)
    monkeypatch.setattr(settings, "DEFAULT_RATE_LIMIT_LIMIT", 3)
    monkeypatch.setattr(settings, "DEFAULT_RATE_LIMIT_PERIOD", 3600)
    monkeypatch.setattr(settings, "TRUSTED_PROXY_HOPS", 1)
    return {"X-Forwarded-For": next(_addresses)}


async def test_a_junk_key_is_throttled_per_address_like_an_anonymous_request(client: AsyncClient, limits: dict):
    """Six of them used to answer 401 six times, each paying for the key lookup."""
    statuses = [(await client.get(THROTTLED_READ, headers={**limits, **JUNK_KEY})).status_code for _ in range(6)]

    assert statuses == [401, 401, 401, 429, 429, 429]


async def test_a_junk_key_and_an_anonymous_request_share_one_budget(client: AsyncClient, limits: dict):
    for _ in range(3):
        await client.get(THROTTLED_READ, headers={**limits, **JUNK_KEY})

    anonymous = await client.get(THROTTLED_READ, headers=limits)

    assert anonymous.status_code == 429


async def test_a_working_key_keeps_its_own_budget_when_junk_spent_the_address(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, limits: dict
):
    """Otherwise anybody could throttle a key holder by sending junk from their address."""
    key = await key_for(db_session, test_user["id"], "user.read")
    for _ in range(4):
        await client.get(THROTTLED_READ, headers={**limits, **JUNK_KEY})

    answer = await client.get(THROTTLED_READ, headers={**limits, **with_key(key)})

    assert answer.status_code == 200


async def test_a_junk_key_never_passes_as_an_anonymous_caller(client: AsyncClient, limits: dict):
    """The throttled routes an anonymous caller may use must not accept one either."""
    signup = {
        "name": "Junk Key",
        "username": f"junkkey{next(_addresses).rsplit('.', 1)[-1]}",
        "email": "junk.key@example.com",
        "password": "Password123!",
    }

    answer = await client.post("/api/v1/users/", json=signup, headers={**limits, **JUNK_KEY})

    assert answer.status_code == 401
