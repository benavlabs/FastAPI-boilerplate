"""Work handed over to run after the answer: when it runs, and what a shutdown waits for."""

import asyncio
import logging

import anyio
import pytest

from src.infrastructure.handover import drain, hand_over

pytestmark = pytest.mark.asyncio


async def test_the_caller_is_not_waiting_for_what_it_handed_over():
    """A request that waited for this would take as long as the work, which is the point."""
    started = asyncio.Event()
    finished: list[str] = []

    async def work() -> None:
        started.set()
        await anyio.sleep(0.05)
        finished.append("done")

    hand_over(work(), name="probe")

    assert finished == []
    await drain()
    assert started.is_set()
    assert finished == ["done"]


async def test_a_shutdown_waits_for_everything_already_handed_over():
    """Dropping them is dropping mail somebody asked for, which is what the queue is for."""
    finished: list[int] = []

    async def work(seat: int) -> None:
        await anyio.sleep(0.01 * seat)
        finished.append(seat)

    for seat in range(4):
        hand_over(work(seat), name=f"probe-{seat}")

    await drain()

    assert sorted(finished) == [0, 1, 2, 3]


async def test_what_it_raises_is_logged_and_goes_no_further(caplog):
    """An exception nobody retrieves is a warning at interpreter exit and nothing else."""

    async def failing() -> None:
        raise RuntimeError("the work went nowhere")

    with caplog.at_level(logging.ERROR):
        hand_over(failing(), name="probe-that-fails")
        await drain()

    assert "probe-that-fails" in caplog.text
    assert "the work went nowhere" in caplog.text


async def test_a_shutdown_gives_up_on_work_that_will_not_finish(caplog):
    """A mail server that ignores its own timeout would hold the shutdown past its grace.

    What is left is counted in the log and nothing of it is named: the message was sealed
    from whoever can read the queue, and a log is no different.

    The call is given a second of its own, so a drain that stopped bounding its wait fails
    this rather than hanging the suite.
    """
    let_it_go = asyncio.Event()

    async def never_finishing() -> None:
        await let_it_go.wait()

    hand_over(never_finishing(), name="probe-that-hangs")

    with caplog.at_level(logging.ERROR), anyio.fail_after(1):
        await drain(within=0.05)

    assert "Gave up on 1 handed-over message(s)" in caplog.text
    let_it_go.set()
    await drain()


async def test_what_finished_before_the_limit_is_not_given_up_on(caplog):
    """The control: the limit is for work that hangs, not for work that takes a moment."""
    finished: list[str] = []

    async def work() -> None:
        await anyio.sleep(0.01)
        finished.append("done")

    hand_over(work(), name="probe-that-finishes")

    with caplog.at_level(logging.ERROR):
        await drain(within=1)

    assert finished == ["done"]
    assert "Gave up" not in caplog.text


async def test_draining_nothing_is_nothing():
    await drain()
