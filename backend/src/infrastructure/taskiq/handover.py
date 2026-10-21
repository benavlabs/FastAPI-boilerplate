"""Work handed over to run after the answer, which a shutdown waits for."""

import asyncio
from collections.abc import Coroutine
from typing import Any

from ..config.settings import get_settings
from ..logging import get_logger
from .constants import BROKER_CONNECT_SECONDS

logger = get_logger()

settings = get_settings()

DRAIN_SECONDS = BROKER_CONNECT_SECONDS + settings.EMAIL_SMTP_TIMEOUT_SECONDS
"""How long a shutdown waits: what one delivery may legitimately take, queue and mail server."""

_handed_over: set[asyncio.Task[None]] = set()
"""What has been handed over and not finished, held so nothing collects a task mid-flight."""


def hand_over(work: Coroutine[Any, Any, None], name: str) -> None:
    """Run ``work`` after the answer rather than before it, under ``name``.

    A reference is kept until it finishes, because a task nothing holds can be collected
    while it runs. Whatever it raises is logged here, so work handed over cannot leave an
    exception nobody retrieves.
    """

    async def logging_whatever_it_raises() -> None:
        try:
            await work
        except Exception:
            logger.exception(f"Work handed over as {name} failed")

    running = asyncio.create_task(logging_whatever_it_raises(), name=name)
    _handed_over.add(running)
    running.add_done_callback(_handed_over.discard)


async def drain(within: float = DRAIN_SECONDS) -> None:
    """Wait for the work already handed over, so a shutdown drops none of it.

    Bounded, because a mail server that ignores its own timeout would otherwise hold the
    shutdown past whatever grace an orchestrator gives it, and be killed mid-delivery
    regardless. What is left is named by its count: a message that waited this long is one
    nobody is getting, and whoever reads the log should know how many.

    ``asyncio.wait`` rather than a cancel scope around ``gather``, because it reports what
    is still running instead of cancelling it on the way out.
    """
    waiting_on = tuple(_handed_over)
    if not waiting_on:
        return

    _, unfinished = await asyncio.wait(waiting_on, timeout=within)
    if unfinished:
        logger.error(f"Gave up on {len(unfinished)} handed-over message(s) after {within}s of shutdown")
