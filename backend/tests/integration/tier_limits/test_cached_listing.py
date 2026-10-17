"""The rate-limit listing is served from the cache, per page, until a write clears it."""

from typing import Any

import pytest
from httpx import AsyncClient

from src.infrastructure.cache.provider import cache_provider
from src.modules.rate_limit.models import RateLimit
from src.modules.rate_limit.routes import RATE_LIMITS_CACHE_PREFIX

pytestmark = pytest.mark.asyncio


class _InProcessCache:
    """A backend that keeps what it is given, so a test can see what was served."""

    def __init__(self) -> None:
        self.stored: dict[str, Any] = {}
        self.reads: list[str] = []

    async def get(self, key: str) -> Any | None:
        self.reads.append(key)

        return self.stored.get(key)

    async def set(self, key: str, value: Any, expiration: int = 3600) -> None:
        self.stored[key] = value

    async def delete(self, key: str) -> None:
        self.stored.pop(key, None)

    async def delete_pattern(self, pattern: str) -> None:
        prefix = pattern.rstrip("*")
        for key in [key for key in self.stored if key.startswith(prefix)]:
            del self.stored[key]


@pytest.fixture
def cached(monkeypatch) -> _InProcessCache:
    """The cache the decorated routes read and write during one test."""
    backend = _InProcessCache()
    monkeypatch.setattr(cache_provider, "get_backend", lambda name=None: backend)

    return backend


async def _listing(client: AsyncClient, **query: int) -> dict[str, Any]:
    response = await client.get("/api/v1/rate-limits/", params=query)
    assert response.status_code == 200, response.text
    listing: dict[str, Any] = response.json()

    return listing


async def test_a_second_read_of_one_page_is_served_from_the_cache(
    superuser_auth_client: AsyncClient, db_session, test_tier: dict, cached: _InProcessCache
):
    db_session.add(RateLimit(tier_id=test_tier["id"], name="first", path="/api/v1/users/", limit=10, period=60))
    await db_session.commit()

    first = await _listing(superuser_auth_client, page=1, items_per_page=10)
    db_session.add(RateLimit(tier_id=test_tier["id"], name="second", path="/api/v1/tiers/", limit=10, period=60))
    await db_session.commit()
    second = await _listing(superuser_auth_client, page=1, items_per_page=10)

    assert second == first
    assert [name for name in cached.stored] == [f"{RATE_LIMITS_CACHE_PREFIX}:1:q=items_per_page=10&page=1"]


async def test_two_pages_do_not_share_an_entry(
    superuser_auth_client: AsyncClient, db_session, test_tier: dict, cached: _InProcessCache
):
    for index in range(3):
        db_session.add(RateLimit(tier_id=test_tier["id"], name=f"limit{index}", path=f"/api/v1/{index}/", limit=10, period=60))
    await db_session.commit()

    first = await _listing(superuser_auth_client, page=1, items_per_page=1)
    second = await _listing(superuser_auth_client, page=2, items_per_page=1)

    assert first["data"] != second["data"]
    assert len(cached.stored) == 2


async def test_a_write_clears_every_cached_page(
    superuser_auth_client: AsyncClient, db_session, test_tier: dict, cached: _InProcessCache
):
    db_session.add(RateLimit(tier_id=test_tier["id"], name="renamed", path="/api/v1/users/", limit=10, period=60))
    await db_session.commit()
    await _listing(superuser_auth_client, page=1, items_per_page=10)
    await _listing(superuser_auth_client, page=2, items_per_page=10)
    assert len(cached.stored) == 2

    updated = await superuser_auth_client.patch("/api/v1/rate-limits/renamed", json={"limit": 99})

    assert updated.status_code == 200
    assert cached.stored == {}
    assert (await _listing(superuser_auth_client, page=1, items_per_page=10))["data"][0]["limit"] == 99
