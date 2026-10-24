"""Opening and closing the broker the API publishes to."""

import asyncio
import logging
from contextlib import suppress

from taskiq_aio_pika import AioPikaBroker

from ..composition import Lifecycle
from ..config.settings import get_settings
from ..handover import drain
from . import brokers
from .constants import BROKER_CONNECT_SECONDS, BROKER_RETRY_SECONDS, BROKER_RETRY_TASK_NAME

logger = logging.getLogger(__name__)

settings = get_settings()

DRAIN_SECONDS = BROKER_CONNECT_SECONDS + settings.EMAIL_SMTP_TIMEOUT_SECONDS
"""How long this shutdown waits: what one delivery may take, queue and mail server."""

_retrying: asyncio.Task[None] | None = None


def broker_connection_is_up() -> bool:
    """Whether the AMQP connection the broker holds is open.

    ``False`` until a startup connects, and from a dropped connection until aio-pika's
    reconnect opens it again. A broker that holds no AMQP connection answers ``False``.
    """
    broker = brokers.default_broker
    if not isinstance(broker, AioPikaBroker) or broker.write_conn is None:
        return False

    return broker.write_conn.connected.is_set()


async def _connection_error() -> Exception | None:
    """Start the broker, closing again what a failed attempt opened, and answer why it failed.

    The attempt is bounded by the broker's own connection timeout, so a host that takes
    the connection and says nothing fails here rather than holding startup open.
    """
    try:
        await brokers.default_broker.startup()
    except Exception as error:
        with suppress(Exception):
            await brokers.default_broker.shutdown()

        return error

    return None


async def _retry_until_connected() -> None:
    """Try the broker again every ``BROKER_RETRY_SECONDS`` until one attempt connects."""
    while True:
        await asyncio.sleep(BROKER_RETRY_SECONDS)
        error = await _connection_error()
        if error is None:
            logger.info("Task broker connected")
            return

        logger.debug(f"Task broker still unreachable: {error}")


async def start_broker() -> None:
    """Connect the default broker, retrying in the background while it is unreachable.

    Does nothing in a taskiq worker process, which the worker CLI starts itself.
    """
    global _retrying

    if brokers.default_broker.is_worker_process:
        return

    error = await _connection_error()
    if error is None:
        return

    logger.warning(f"Task broker unreachable, retrying every {BROKER_RETRY_SECONDS}s: {error}")
    _retrying = asyncio.create_task(_retry_until_connected(), name=BROKER_RETRY_TASK_NAME)


async def stop_broker() -> None:
    """Stop the retries, then close whatever the broker opened.

    The work handed over to run after an answer is drained before this, so a message on its
    way to the queue is not dropped by the shutdown that was meant to let it finish.
    """
    global _retrying

    if brokers.default_broker.is_worker_process:
        return

    if _retrying is not None:
        _retrying.cancel()
        with suppress(asyncio.CancelledError):
            await _retrying
        _retrying = None

    await brokers.default_broker.shutdown()


async def drain_what_was_handed_over() -> None:
    """Wait for the messages on their way to the queue, for as long as that may take."""
    await drain(DRAIN_SECONDS)


lifecycle = Lifecycle("taskiq", startup=start_broker, shutdown=(drain_what_was_handed_over, stop_broker))
