"""Whether the task broker is reachable."""

from collections.abc import Awaitable
from typing import cast

from redis.asyncio import Redis

from ..composition import ReadinessCheck
from ..config.enums import TaskiqBrokerType
from ..config.settings import settings
from .lifecycle import broker_connection_is_up


async def broker_is_reachable() -> None:
    """Raise unless the broker answers: a Redis ping, or the connection the app keeps open.

    A RabbitMQ broker is reported on over the connection the app's lifespan opened: ready
    while that connection is up, unavailable while it is being opened or reconnected.
    """
    if settings.TASKIQ_BROKER_TYPE == TaskiqBrokerType.RABBITMQ.value:
        if not broker_connection_is_up():
            raise ConnectionError("The task broker is not connected")

        return

    if settings.TASKIQ_BROKER_TYPE != TaskiqBrokerType.REDIS.value:
        return

    client = Redis.from_url(settings.TASKIQ_BROKER_URL)
    try:
        await cast(Awaitable[bool], client.ping())
    finally:
        await client.aclose()


def broker_target() -> str | None:
    """The broker this project publishes to."""
    return settings.TASKIQ_BROKER_URL


readiness = ReadinessCheck("task_broker", broker_is_reachable, target=broker_target)
