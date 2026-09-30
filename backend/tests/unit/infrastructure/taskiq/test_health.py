"""The broker readiness check covers the Redis broker the API actually publishes to."""

import pytest

from src.infrastructure.config.settings import settings
from src.infrastructure.taskiq import health

pytestmark = pytest.mark.asyncio


async def test_a_rabbitmq_broker_is_left_alone(monkeypatch):
    """The API never opens it, so a probe would report on a connection nothing makes."""
    monkeypatch.setattr(settings, "TASKIQ_BROKER_TYPE", "rabbitmq")

    await health.broker_is_reachable()

    assert health.broker_target() is None


async def test_the_redis_broker_is_pinged(monkeypatch):
    pings: list[bool] = []

    class _Client:
        async def ping(self) -> bool:
            pings.append(True)
            return True

        async def aclose(self) -> None:
            return None

    monkeypatch.setattr(settings, "TASKIQ_BROKER_TYPE", "redis")
    monkeypatch.setattr(health.Redis, "from_url", classmethod(lambda cls, url, **kwargs: _Client()))

    await health.broker_is_reachable()

    assert pings == [True]
    assert health.broker_target().startswith("redis://")
