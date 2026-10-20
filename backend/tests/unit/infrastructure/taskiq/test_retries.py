"""How a task that asks to be retried is retried, and what the scheduler has to read."""

from datetime import UTC, datetime
from typing import Any

import pytest
from taskiq import InMemoryBroker, ScheduledTask, ScheduleSource
from taskiq.message import TaskiqMessage
from taskiq.middlewares import SimpleRetryMiddleware, SmartRetryMiddleware
from taskiq.result import TaskiqResult
from taskiq.schedule_sources import LabelScheduleSource
from taskiq_redis import ListRedisScheduleSource

from src.infrastructure.config.enums import TaskiqBrokerType
from src.infrastructure.taskiq import retries
from src.infrastructure.taskiq.constants import RETRY_MAX_DELAY_SECONDS, RETRY_SCHEDULE_PREFIX
from src.infrastructure.taskiq.retries import retry_middleware, retry_schedule_source, schedule_sources

A_DELAY = 30

FAILED = TaskiqMessage(task_id="task-1", task_name="email:send", labels={"retry_on_error": True}, args=[], kwargs={})


class _Holding(ScheduleSource):
    """A schedule source that keeps what it was asked to hold."""

    def __init__(self) -> None:
        self.held: list[ScheduledTask] = []

    async def get_schedules(self) -> list[ScheduledTask]:
        return self.held

    async def add_schedule(self, schedule: ScheduledTask) -> None:
        self.held.append(schedule)


@pytest.fixture
def a_delay(monkeypatch) -> int:
    """A project that asked for its retries to wait."""
    monkeypatch.setattr(retries.settings, "TASKIQ_RETRY_DELAY_SECONDS", A_DELAY)

    return A_DELAY


def test_retries_are_immediate_unless_a_delay_is_configured():
    """Nothing reads a schedule unless a scheduler runs, so a delay is asked for, not assumed."""
    assert retry_schedule_source() is None
    assert isinstance(retry_middleware(None), SimpleRetryMiddleware)


def test_a_configured_delay_is_held_in_the_queues_own_redis(a_delay: int, monkeypatch):
    """The worker writes a retry where the scheduler reads it, so both have to name one place."""
    built: list[dict[str, Any]] = []

    def recording(**options: Any) -> ScheduleSource:
        built.append(options)

        return _Holding()

    monkeypatch.setattr(retries, "ListRedisScheduleSource", recording)

    retry_schedule_source()

    assert built == [{"url": retries.settings.TASKIQ_BROKER_URL, "prefix": RETRY_SCHEDULE_PREFIX}]


def test_the_source_is_the_one_taskiq_still_supports(a_delay: int):
    """``RedisScheduleSource`` is deprecated in favour of the list one."""
    assert isinstance(retry_schedule_source(), ListRedisScheduleSource)


def test_a_delay_on_a_broker_with_nowhere_to_hold_a_retry_is_refused(a_delay: int, monkeypatch):
    """A rabbitmq queue is configured with no Redis, and a retry has to wait somewhere."""
    monkeypatch.setattr(retries.settings, "TASKIQ_BROKER_TYPE", TaskiqBrokerType.RABBITMQ.value)

    with pytest.raises(ValueError, match="TASKIQ_RETRY_DELAY_SECONDS"):
        retry_schedule_source()


def test_the_delayed_middleware_grows_the_wait_and_scatters_it(a_delay: int):
    middleware = retry_middleware(_Holding())

    assert isinstance(middleware, SmartRetryMiddleware)
    assert middleware.default_delay == a_delay
    assert (middleware.use_delay_exponent, middleware.max_delay_exponent) == (True, RETRY_MAX_DELAY_SECONDS)
    assert middleware.use_jitter is True


@pytest.mark.asyncio
async def test_a_failed_task_is_held_until_its_delay_has_passed(a_delay: int):
    """The retry is scheduled rather than requeued, which is what makes it wait at all."""
    holding = _Holding()
    middleware = retry_middleware(holding)
    middleware.set_broker(InMemoryBroker())

    asked_at = datetime.now(UTC)
    scheduling = middleware.on_error(FAILED, TaskiqResult(is_err=True, return_value=None, execution_time=0.1), ValueError("no"))

    assert scheduling is not None
    await scheduling

    held: Any = holding.held[0]
    assert held.task_name == "email:send"
    assert held.time is not None and (held.time - asked_at).total_seconds() >= a_delay


def test_the_scheduler_reads_the_labels_and_nothing_else_by_default():
    sources = schedule_sources(InMemoryBroker())

    assert [type(source) for source in sources] == [LabelScheduleSource]


def test_the_scheduler_reads_the_delayed_retries_as_well(a_delay: int):
    """The worker holds them and the scheduler enqueues them, so it has to read the same place."""
    sources = schedule_sources(InMemoryBroker())

    assert [type(source) for source in sources] == [LabelScheduleSource, ListRedisScheduleSource]
