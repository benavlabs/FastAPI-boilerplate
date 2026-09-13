"""Taskiq app configuration and worker lifecycle management."""

import logging

from taskiq import AsyncBroker
from taskiq.events import TaskiqEvents
from taskiq.state import TaskiqState

from .deps import dispose_taskiq_engine

logger = logging.getLogger(__name__)


async def startup_taskiq_worker(state: TaskiqState) -> None:
    """Initialize worker startup procedures.

    Args:
        state: The taskiq state instance
    """
    logger.info("Starting taskiq worker...")
    logger.info("Taskiq worker startup complete")


async def shutdown_taskiq_worker(state: TaskiqState) -> None:
    """Cleanup worker shutdown procedures.

    Args:
        state: The taskiq state instance
    """
    logger.info("Shutting down taskiq worker...")
    await dispose_taskiq_engine()
    logger.info("Taskiq worker shutdown complete")


def configure_broker_lifecycle(broker: AsyncBroker) -> None:
    """Configure broker with startup and shutdown handlers.

    Args:
        broker: The broker to configure
    """
    broker.add_middlewares()
    broker.add_event_handler(TaskiqEvents.WORKER_STARTUP, startup_taskiq_worker)
    broker.add_event_handler(TaskiqEvents.WORKER_SHUTDOWN, shutdown_taskiq_worker)
