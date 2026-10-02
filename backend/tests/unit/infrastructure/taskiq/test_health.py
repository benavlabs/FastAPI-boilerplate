"""The broker readiness check covers the Redis broker the API actually publishes to."""

import anyio
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
    target = health.broker_target()
    assert target is not None and target.startswith("redis://")


async def test_a_blackholed_redis_broker_times_out(monkeypatch):
    """A real client against an address nothing answers on, bounded as the probe bounds it."""
    monkeypatch.setattr(settings, "TASKIQ_BROKER_TYPE", "redis")
    monkeypatch.setattr(settings, "TASKIQ_REDIS_HOST", "10.255.255.1")
    monkeypatch.setattr(settings, "TASKIQ_REDIS_PORT", 6379)
    monkeypatch.setattr(settings, "TASKIQ_REDIS_PASSWORD", None)

    with pytest.raises(TimeoutError), anyio.fail_after(0.5):
        await health.broker_is_reachable()
