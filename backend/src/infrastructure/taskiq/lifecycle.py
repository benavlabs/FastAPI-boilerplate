"""Opening and closing the broker the API publishes to."""

import asyncio
import logging
from contextlib import suppress

from taskiq_aio_pika import AioPikaBroker

from ..composition import Lifecycle
from . import brokers
from .constants import BROKER_RETRY_SECONDS, BROKER_RETRY_TASK_NAME

logger = logging.getLogger(__name__)

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
    """Start the broker, closing again what a failed attempt opened, and answer why it failed."""
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
    """Stop the retries, then close whatever the broker opened."""
    global _retrying

    if brokers.default_broker.is_worker_process:
        return

    if _retrying is not None:
        _retrying.cancel()
        with suppress(asyncio.CancelledError):
            await _retrying
        _retrying = None

    await brokers.default_broker.shutdown()


lifecycle = Lifecycle("taskiq", startup=start_broker, shutdown=(stop_broker,))
