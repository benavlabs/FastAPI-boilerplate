"""Whether the task broker is reachable."""

from collections.abc import Awaitable
from typing import cast

from redis.asyncio import Redis

from ..composition import ReadinessCheck
from ..config.enums import TaskiqBrokerType
from ..config.settings import settings


async def broker_is_reachable() -> None:
    """Raise unless the Redis broker answers; a RabbitMQ broker is not probed."""
    if settings.TASKIQ_BROKER_TYPE != TaskiqBrokerType.REDIS.value:
        return

    client = Redis.from_url(settings.TASKIQ_BROKER_URL)
    try:
        await cast(Awaitable[bool], client.ping())
    finally:
        await client.aclose()


def broker_target() -> str | None:
    """The broker this project publishes to."""
    return settings.TASKIQ_BROKER_URL if settings.TASKIQ_BROKER_TYPE == TaskiqBrokerType.REDIS.value else None


readiness = ReadinessCheck("task_broker", broker_is_reachable, target=broker_target)
