"""Taskiq broker configuration and initialization."""

import importlib
from importlib.util import find_spec

from taskiq import AsyncBroker
from taskiq.serializers import JSONSerializer
from taskiq_redis import ListQueueBroker, RedisAsyncResultBackend

from ..config.enums import TaskiqBrokerType
from ..config.settings import get_settings
from ..redis import redis_url
from .constants import BROKER_CONNECT_SECONDS, RESULT_KEPT_SECONDS

settings = get_settings()


def create_default_broker() -> AsyncBroker:
    """Create email broker for taskiq based on configured broker type.

    Returns:
        Configured AsyncBroker instance for email tasks (Redis or RabbitMQ)
    """
    if settings.TASKIQ_BROKER_TYPE == TaskiqBrokerType.REDIS.value:
        return _create_redis_broker()
    elif settings.TASKIQ_BROKER_TYPE == TaskiqBrokerType.RABBITMQ.value:
        return _create_rabbitmq_broker()
    else:
        raise ValueError(f"Unsupported broker type: {settings.TASKIQ_BROKER_TYPE}")


def _create_redis_broker() -> AsyncBroker:
    """Create Redis-based broker for taskiq.

    The connect timeout is the broker's own: redis-py leaves it unset, so a host that does
    not answer holds a caller for as long as the operating system takes to give up on the
    connection. Bounded, an unreachable queue fails within ``BROKER_CONNECT_SECONDS`` and
    the caller can do something about it.

    A read timeout belongs to the caller rather than the connection: the worker waits for
    its next job in a ``brpop`` with no timeout of its own, so a socket that stops waiting
    raises ``redis.exceptions.TimeoutError`` out of the listener the first time the queue
    is idle for that long, and nothing in that loop catches it. What the sender needs is a
    bound on its own enqueue, which it has.

    A result expires after ``RESULT_KEPT_SECONDS``, so the results nothing ever came back
    for leave the Redis the queue itself runs on rather than filling it for good.
    """
    redis_host = settings.TASKIQ_REDIS_HOST
    redis_port = settings.TASKIQ_REDIS_PORT
    redis_db = settings.TASKIQ_REDIS_DB
    redis_password = settings.TASKIQ_REDIS_PASSWORD

    url = redis_url(redis_host, redis_port, redis_db, redis_password)

    broker = ListQueueBroker(
        url=url,
        queue_name="default",
        socket_connect_timeout=BROKER_CONNECT_SECONDS,
    ).with_result_backend(
        RedisAsyncResultBackend(redis_url=url, serializer=JSONSerializer(), result_ex_time=RESULT_KEPT_SECONDS)
    )

    return broker


RABBITMQ_MODULE = f"{__package__}.rabbitmq"


def _create_rabbitmq_broker() -> AsyncBroker:
    """The broker ``.rabbitmq`` builds, loaded by name: a project on redis has neither it nor taskiq-aio-pika."""
    if find_spec(RABBITMQ_MODULE) is None:
        raise ImportError(
            "TASKIQ_BROKER_TYPE=rabbitmq needs taskiq-aio-pika and the rabbitmq broker, which a project gets "
            "by being generated with taskiq.broker=rabbitmq."
        )

    broker: AsyncBroker = importlib.import_module(RABBITMQ_MODULE).create_broker()

    return broker


default_broker = create_default_broker()
