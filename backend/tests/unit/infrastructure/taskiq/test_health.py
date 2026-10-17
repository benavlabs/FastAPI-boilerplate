"""The broker readiness check covers the broker the API actually publishes to."""

import anyio
import pytest

from src.infrastructure.config.settings import settings
from src.infrastructure.taskiq import health
from tests.silent_server import silent_server

pytestmark = pytest.mark.asyncio


async def test_a_rabbitmq_broker_nothing_connected_is_unavailable(monkeypatch):
    """No lifespan has opened the broker in this process, which is what the check reports on."""
    monkeypatch.setattr(settings, "TASKIQ_BROKER_TYPE", "rabbitmq")

    with pytest.raises(ConnectionError):
        await health.broker_is_reachable()

    target = health.broker_target()
    assert target is not None and target.startswith("amqp://")


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


async def test_a_redis_broker_that_never_answers_times_out(monkeypatch):
    """A real client against a server that takes the connection and says nothing."""
    monkeypatch.setattr(settings, "TASKIQ_BROKER_TYPE", "redis")
    monkeypatch.setattr(settings, "TASKIQ_REDIS_HOST", "127.0.0.1")
    monkeypatch.setattr(settings, "TASKIQ_REDIS_PASSWORD", None)

    async with silent_server() as port:
        monkeypatch.setattr(settings, "TASKIQ_REDIS_PORT", port)

        with pytest.raises(TimeoutError), anyio.fail_after(0.5):
            await health.broker_is_reachable()
