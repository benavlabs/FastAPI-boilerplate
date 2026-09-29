"""Taskiq broker configuration and initialization."""

from taskiq import AsyncBroker
from taskiq_aio_pika import AioPikaBroker
from taskiq_redis import ListQueueBroker, RedisAsyncResultBackend

from ..config.enums import TaskiqBrokerType
from ..config.settings import get_settings

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
    """Create Redis-based broker for taskiq."""
    redis_host = settings.TASKIQ_REDIS_HOST
    redis_port = settings.TASKIQ_REDIS_PORT
    redis_db = settings.TASKIQ_REDIS_DB
    redis_password = settings.TASKIQ_REDIS_PASSWORD

    password_part = f":{redis_password}@" if redis_password else ""
    redis_url = f"redis://{password_part}{redis_host}:{redis_port}/{redis_db}"

    broker = ListQueueBroker(url=redis_url, queue_name="default").with_result_backend(
        RedisAsyncResultBackend(redis_url=redis_url)
    )

    return broker


def _create_rabbitmq_broker() -> AsyncBroker:
    """Create RabbitMQ-based broker for taskiq."""
    rabbitmq_url = settings.TASKIQ_BROKER_URL

    broker = AioPikaBroker(url=rabbitmq_url, queue_name="default")

    return broker


default_broker = create_default_broker()
