"""Starting and stopping the broker the API publishes to, whichever broker it is."""

import asyncio

import pytest

from src.infrastructure import handover
from src.infrastructure.config.enums import TaskiqBrokerType
from src.infrastructure.taskiq import brokers, lifecycle
from src.infrastructure.taskiq.constants import BROKER_CONNECT_SECONDS

RETRY_SECONDS = 0.01
WITHIN_SECONDS = 5


class _Broker:
    """A broker whose first ``failures`` startups raise, counting what it is asked to do."""

    def __init__(self, failures: int = 0, is_worker_process: bool = False) -> None:
        self.failures = failures
        self.is_worker_process = is_worker_process
        self.startups = 0
        self.shutdowns = 0
        self.connected = asyncio.Event()

    async def startup(self) -> None:
        self.startups += 1
        if self.startups <= self.failures:
            raise ConnectionError("refused")
        self.connected.set()

    async def shutdown(self) -> None:
        self.shutdowns += 1


@pytest.fixture
def broker(monkeypatch):
    def install(**kwargs) -> _Broker:
        stub = _Broker(**kwargs)
        monkeypatch.setattr(brokers, "default_broker", stub)
        monkeypatch.setattr(lifecycle, "BROKER_RETRY_SECONDS", RETRY_SECONDS)
        monkeypatch.setattr(lifecycle, "_retrying", None)
        return stub

    return install


def test_the_shutdown_drains_what_was_handed_over_before_it_closes_the_broker():
    """A message handed over finds a closed broker otherwise, and falls back to SMTP or is lost.

    ``lifespan_factory`` runs a lifecycle's shutdowns in the order the tuple gives them,
    which ``test_app_factory`` pins.
    """
    assert lifecycle.lifecycle.shutdown == (lifecycle.drain_what_was_handed_over, lifecycle.stop_broker)


def test_this_shutdown_waits_for_the_queue_leg_as_well_as_the_delivery():
    """A message handed over here may spend the broker's budget and then the mail server's."""
    assert lifecycle.DRAIN_SECONDS > handover.DRAIN_SECONDS
    assert lifecycle.DRAIN_SECONDS == BROKER_CONNECT_SECONDS + handover.DRAIN_SECONDS


async def test_a_worker_process_leaves_the_broker_to_the_taskiq_cli(broker):
    stub = broker(is_worker_process=True)

    await lifecycle.start_broker()
    await lifecycle.stop_broker()

    assert stub.startups == stub.shutdowns == 0


async def test_a_failed_attempt_closes_what_its_startup_opened_and_the_retry_connects(broker):
    stub = broker(failures=2)

    await lifecycle.start_broker()
    await asyncio.wait_for(stub.connected.wait(), WITHIN_SECONDS)
    await lifecycle.stop_broker()

    assert stub.startups == 3
    assert stub.shutdowns == 2 + 1


async def test_the_retry_stops_with_the_app(broker):
    stub = broker(failures=10**6)

    await lifecycle.start_broker()
    stopping = asyncio.create_task(lifecycle.stop_broker())
    done, _ = await asyncio.wait({stopping}, timeout=WITHIN_SECONDS)
    if not done:
        stopping.cancel()
        if lifecycle._retrying is not None:
            lifecycle._retrying.cancel()

    assert done == {stopping}
    assert [task for task in asyncio.all_tasks() if task.get_name() == lifecycle.BROKER_RETRY_TASK_NAME] == []
    assert stub.shutdowns >= 2


def test_only_a_rabbitmq_broker_is_asked_about_an_amqp_connection(monkeypatch):
    """A project on redis has no ``.rabbitmq`` to ask."""
    monkeypatch.setattr(lifecycle.settings, "TASKIQ_BROKER_TYPE", TaskiqBrokerType.REDIS.value)
    monkeypatch.setattr(brokers, "RABBITMQ_MODULE", f"{brokers.__package__}.not_generated")

    assert lifecycle.broker_connection_is_up() is False
