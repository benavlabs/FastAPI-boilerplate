"""Taskiq broker configuration and initialization."""

from taskiq import AsyncBroker
from taskiq.serializers import JSONSerializer
from taskiq_aio_pika import AioPikaBroker
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

    A result expires after ``RESULT_KEPT_SECONDS``, so the results nothing ever came back
    for leave the Redis the queue itself runs on rather than filling it for good.
    """
    redis_host = settings.TASKIQ_REDIS_HOST
    redis_port = settings.TASKIQ_REDIS_PORT
    redis_db = settings.TASKIQ_REDIS_DB
    redis_password = settings.TASKIQ_REDIS_PASSWORD

    url = redis_url(redis_host, redis_port, redis_db, redis_password)

    broker = ListQueueBroker(url=url, queue_name="default").with_result_backend(
        RedisAsyncResultBackend(redis_url=url, serializer=JSONSerializer(), result_ex_time=RESULT_KEPT_SECONDS)
    )

    return broker


def _create_rabbitmq_broker() -> AsyncBroker:
    """Create RabbitMQ-based broker for taskiq, on the queue ``AioPikaBroker`` names by default.

    ``timeout`` reaches aio-pika's ``connect_robust`` through the broker's connection
    keywords, so a host that accepts the socket and says nothing fails the attempt within
    ``BROKER_CONNECT_SECONDS`` rather than holding it open.
    """
    rabbitmq_url = settings.TASKIQ_BROKER_URL

    broker = AioPikaBroker(url=rabbitmq_url, timeout=BROKER_CONNECT_SECONDS)

    return broker


default_broker = create_default_broker()
