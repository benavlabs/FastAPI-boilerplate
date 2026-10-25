"""What the worker entry point configures on the broker."""

import pytest
from taskiq import InMemoryBroker

from src.infrastructure.config.settings import settings
from src.infrastructure.taskiq.app import configure_broker_lifecycle

pytestmark = pytest.mark.asyncio


@pytest.fixture
def worker_broker(monkeypatch):
    """A broker configured the way ``worker.py`` configures the project's own."""

    def configured(retry_count: int) -> InMemoryBroker:
        monkeypatch.setattr(settings, "TASKIQ_DEFAULT_RETRY_COUNT", retry_count)
        broker = InMemoryBroker(await_inplace=True)
        configure_broker_lifecycle(broker)

        return broker

    return configured


class TestRetries:
    """A task that asks to be retried is, as many times as the setting allows."""

    async def test_a_task_that_fails_twice_then_succeeds_runs_three_times(self, worker_broker):
        runs: list[str] = []
        broker = worker_broker(3)

        @broker.task(task_name="tests.fails_twice", retry_on_error=True)
        async def fails_twice() -> str:
            runs.append("run")
            if len(runs) < 3:
                raise RuntimeError("not yet")

            return "done"

        await broker.startup()
        await fails_twice.kiq()

        assert len(runs) == 3

    async def test_the_count_at_zero_runs_a_failing_task_once(self, worker_broker):
        runs: list[str] = []
        broker = worker_broker(0)

        @broker.task(task_name="tests.never_retried", retry_on_error=True)
        async def never_retried() -> None:
            runs.append("run")
            raise RuntimeError("always")

        await broker.startup()
        await never_retried.kiq()

        assert len(runs) == 1

    async def test_a_task_that_does_not_ask_for_retries_runs_once(self, worker_broker):
        runs: list[str] = []
        broker = worker_broker(3)

        @broker.task(task_name="tests.not_opted_in")
        async def not_opted_in() -> None:
            runs.append("run")
            raise RuntimeError("always")

        await broker.startup()
        await not_opted_in.kiq()

        assert len(runs) == 1
