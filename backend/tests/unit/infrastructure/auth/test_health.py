"""The servers accounts needs: the lockout's Redis and the one holding sessions."""

import pytest

from src.infrastructure.auth import health
from src.infrastructure.config.settings import settings

pytestmark = pytest.mark.asyncio


async def test_an_in_process_limiter_is_nothing_to_report(monkeypatch):
    async def refuse() -> bool:
        raise AssertionError("the memory limiter has nothing to reach")

    monkeypatch.setattr(settings, "RATE_LIMITER_BACKEND", "memory")
    monkeypatch.setattr(health.rate_limiter_redis_client, "ping", refuse)

    await health.limiter_is_reachable()

    assert health.limiter_target() is None


async def test_the_limiters_redis_is_pinged(monkeypatch):
    pings: list[bool] = []

    async def ping() -> bool:
        pings.append(True)
        return True

    monkeypatch.setattr(settings, "RATE_LIMITER_BACKEND", "redis")
    monkeypatch.setattr(health.rate_limiter_redis_client, "ping", ping)

    await health.limiter_is_reachable()

    assert pings == [True]
    target = health.limiter_target()
    assert target is not None and target.startswith("redis://")


async def test_an_unreachable_limiter_raises(monkeypatch):
    """The login lockout fails closed, so this outage refuses every login."""

    async def refuse() -> bool:
        raise ConnectionRefusedError("nothing listening")

    monkeypatch.setattr(settings, "RATE_LIMITER_BACKEND", "redis")
    monkeypatch.setattr(health.rate_limiter_redis_client, "ping", refuse)

    with pytest.raises(ConnectionRefusedError):
        await health.limiter_is_reachable()


async def test_memory_sessions_are_nothing_to_report(monkeypatch):
    monkeypatch.setattr(settings, "SESSION_BACKEND", "memory")

    await health.sessions_are_reachable()

    assert health.sessions_target() is None


async def test_the_session_redis_is_pinged_and_closed(monkeypatch):
    closed: list[bool] = []

    class _Client:
        async def ping(self) -> bool:
            return True

        async def aclose(self) -> None:
            closed.append(True)

    monkeypatch.setattr(settings, "SESSION_BACKEND", "redis")
    monkeypatch.setattr(health.Redis, "from_url", classmethod(lambda cls, url, **kwargs: _Client()))

    await health.sessions_are_reachable()

    assert closed == [True]
    assert health.sessions_target() == settings.SESSION_REDIS_URL


async def test_an_unreachable_session_redis_raises_and_still_closes(monkeypatch):
    closed: list[bool] = []

    class _Client:
        async def ping(self) -> bool:
            raise ConnectionRefusedError("nothing listening")

        async def aclose(self) -> None:
            closed.append(True)

    monkeypatch.setattr(settings, "SESSION_BACKEND", "redis")
    monkeypatch.setattr(health.Redis, "from_url", classmethod(lambda cls, url, **kwargs: _Client()))

    with pytest.raises(ConnectionRefusedError):
        await health.sessions_are_reachable()

    assert closed == [True]
