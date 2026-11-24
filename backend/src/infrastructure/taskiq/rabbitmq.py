"""The RabbitMQ broker, which a project has by being generated with ``taskiq.broker=rabbitmq``."""

from taskiq import AsyncBroker
from taskiq_aio_pika import AioPikaBroker

from ..config.settings import get_settings
from .constants import BROKER_CONNECT_SECONDS

settings = get_settings()


def create_broker() -> AsyncBroker:
    """Create RabbitMQ-based broker for taskiq, on the queue ``AioPikaBroker`` names by default.

    ``timeout`` reaches aio-pika's ``connect_robust`` through the broker's connection
    keywords, so a host that accepts the socket and says nothing fails the attempt within
    ``BROKER_CONNECT_SECONDS`` rather than holding it open.
    """
    return AioPikaBroker(url=settings.TASKIQ_BROKER_URL, timeout=BROKER_CONNECT_SECONDS)


def connection_is_up(broker: AsyncBroker) -> bool:
    """Whether the AMQP connection ``broker`` holds is open.

    ``False`` until a startup connects, and from a dropped connection until aio-pika's
    reconnect opens it again. A broker that holds no AMQP connection answers ``False``.
    """
    if not isinstance(broker, AioPikaBroker) or broker.write_conn is None:
        return False

    return broker.write_conn.connected.is_set()
