"""The schedules the scheduler process picks up."""

import pytest

from src.infrastructure.taskiq.brokers import default_broker
from src.infrastructure.taskiq.scheduler import scheduler

pytestmark = pytest.mark.asyncio

EVERY_FIVE_MINUTES = "*/5 * * * *"


@pytest.fixture
def scheduled_task():
    """A task of this project's own, declaring when it should run."""
    name = "tests.scheduled_every_five_minutes"

    @default_broker.task(task_name=name, schedule=[{"cron": EVERY_FIVE_MINUTES}])
    async def scheduled_every_five_minutes() -> None:
        pass

    yield name

    default_broker.local_task_registry.pop(name, None)


async def test_the_scheduler_finds_what_a_task_declares(scheduled_task: str):
    """The scheduler reads the ``schedule`` label off the tasks the worker registers."""
    for source in scheduler.sources:
        await source.startup()

    found = [(task.task_name, task.cron) for source in scheduler.sources for task in await source.get_schedules()]

    assert (scheduled_task, EVERY_FIVE_MINUTES) in found


async def test_the_scheduler_kicks_on_the_project_broker():
    assert scheduler.broker is default_broker
