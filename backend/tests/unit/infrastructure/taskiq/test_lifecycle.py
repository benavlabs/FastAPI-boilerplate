"""Enqueueing from the API process, over a real RabbitMQ broker."""

import asyncio
import socket

import pytest
from fastapi import FastAPI
from taskiq import AsyncBroker, TaskiqEvents
from taskiq.decor import AsyncTaskiqDecoratedTask
from taskiq.exceptions import SendTaskError
from taskiq.state import TaskiqState
from testcontainers.core.container import DockerContainer
from testcontainers.core.wait_strategies import LogMessageWaitStrategy

from src.infrastructure.app_factory import lifespan_factory
from src.infrastructure.config.enums import TaskiqBrokerType
from src.infrastructure.config.settings import settings
from src.infrastructure.taskiq import brokers, lifecycle
from src.infrastructure.taskiq.constants import BROKER_RETRY_TASK_NAME
from src.infrastructure.taskiq.lifecycle import start_broker
from src.wiring.app import LIFECYCLES
from tests.conftest import is_docker_running

RABBITMQ_IMAGE = "rabbitmq:4-alpine"
RETRY_SECONDS = 0.2
CONNECTED_WITHIN_SECONDS = 30
ATTEMPTS_WITHIN_SECONDS = 5


def _ready_container(port: int | None = None) -> DockerContainer:
    ready = LogMessageWaitStrategy("Server startup complete").with_startup_timeout(180)
    container = DockerContainer(RABBITMQ_IMAGE).waiting_for(ready)

    return container.with_exposed_ports(5672) if port is None else container.with_bind_ports(5672, port)


def _closed_port() -> int:
    """A port nothing listens on, so a connection to it is refused at once."""
    with socket.socket() as finder:
        finder.bind(("127.0.0.1", 0))

        return int(finder.getsockname()[1])


def _broker_pointed_at(monkeypatch, host: str, port: int) -> AsyncBroker:
    """The broker this project builds for RabbitMQ, as the wiring's lifecycle sees it."""
    monkeypatch.setattr(brokers.settings, "TASKIQ_BROKER_TYPE", TaskiqBrokerType.RABBITMQ.value)
    monkeypatch.setattr(brokers.settings, "TASKIQ_RABBITMQ_HOST", host)
    monkeypatch.setattr(brokers.settings, "TASKIQ_RABBITMQ_PORT", port)
    monkeypatch.setattr(lifecycle, "BROKER_RETRY_SECONDS", RETRY_SECONDS)

    broker = brokers.create_default_broker()
    monkeypatch.setattr(brokers, "default_broker", broker)

    return broker


def _task(broker: AsyncBroker, name: str) -> AsyncTaskiqDecoratedTask:
    @broker.task(task_name=name)
    async def enqueued() -> None:
        pass

    return enqueued


def _app_lifespan():
    return lifespan_factory(settings, create_tables_on_startup=False, lifecycles=LIFECYCLES)


def _counted_client_events(broker: AsyncBroker, until: int) -> tuple[dict[str, int], asyncio.Event]:
    """Stub client handlers, counting the startups and shutdowns the broker runs them for."""
    runs = {"startup": 0, "shutdown": 0}
    counted = asyncio.Event()

    async def record_startup(state: TaskiqState) -> None:
        runs["startup"] += 1

    async def record_shutdown(state: TaskiqState) -> None:
        runs["shutdown"] += 1
        if runs["shutdown"] >= until:
            counted.set()

    broker.add_event_handler(TaskiqEvents.CLIENT_STARTUP, record_startup)
    broker.add_event_handler(TaskiqEvents.CLIENT_SHUTDOWN, record_shutdown)

    return runs, counted


def _retries_running() -> list[asyncio.Task]:
    return [task for task in asyncio.all_tasks() if task.get_name() == BROKER_RETRY_TASK_NAME]


async def _kiq_once_connected(task: AsyncTaskiqDecoratedTask):
    """Enqueue as soon as the retry has connected, giving up after a bounded wait."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + CONNECTED_WITHIN_SECONDS
    while True:
        try:
            return await task.kiq()
        except SendTaskError:
            if loop.time() >= deadline:
                raise
            await asyncio.sleep(RETRY_SECONDS)


@pytest.fixture(scope="module", autouse=True)
def docker_required():
    if not is_docker_running():
        pytest.skip("Docker is required, but not running")


@pytest.fixture(scope="module")
def rabbitmq():
    """A RabbitMQ broker of this module's own, accepting connections."""
    with _ready_container() as container:
        yield container


@pytest.fixture
async def rabbitmq_broker(rabbitmq, monkeypatch):
    broker = _broker_pointed_at(monkeypatch, rabbitmq.get_container_host_ip(), int(rabbitmq.get_exposed_port(5672)))

    yield broker

    await broker.shutdown()


async def test_an_enqueue_while_the_app_runs_reaches_the_broker(rabbitmq_broker: AsyncBroker):
    task = _task(rabbitmq_broker, "tests.enqueued_while_running")
    lifespan = _app_lifespan()

    async with lifespan(FastAPI()):
        kicked = await task.kiq()

    assert kicked.task_id


async def test_the_broker_is_closed_when_the_app_stops(rabbitmq_broker: AsyncBroker):
    task = _task(rabbitmq_broker, "tests.enqueued_after_shutdown")
    lifespan = _app_lifespan()

    async with lifespan(FastAPI()):
        assert await task.kiq()

    with pytest.raises(SendTaskError):
        await task.kiq()


async def test_a_worker_process_leaves_the_broker_to_the_taskiq_cli(rabbitmq_broker: AsyncBroker):
    """The worker's own startup opens the connection; the app's would open a second one."""
    task = _task(rabbitmq_broker, "tests.enqueued_from_a_worker")
    rabbitmq_broker.is_worker_process = True

    await start_broker()

    with pytest.raises(SendTaskError):
        await task.kiq()


class TestABrokerThatIsDownAtStartup:
    """The broker is an informational dependency: the API serves without it."""

    async def test_the_app_starts_and_only_the_enqueue_fails(self, monkeypatch):
        broker = _broker_pointed_at(monkeypatch, "127.0.0.1", _closed_port())
        task = _task(broker, "tests.enqueued_while_down")
        lifespan = _app_lifespan()

        async with lifespan(FastAPI()):
            with pytest.raises(SendTaskError):
                await task.kiq()

    async def test_the_retry_connects_once_the_broker_comes_up(self, monkeypatch):
        port = _closed_port()
        broker = _broker_pointed_at(monkeypatch, "127.0.0.1", port)
        task = _task(broker, "tests.enqueued_after_a_retry")
        lifespan = _app_lifespan()

        async with lifespan(FastAPI()):
            with _ready_container(port):
                kicked = await _kiq_once_connected(task)

        assert kicked.task_id

    async def test_a_failed_attempt_closes_what_its_startup_opened(self, monkeypatch):
        """Both failed attempts ran the base startup work, and each one was closed again."""
        broker = _broker_pointed_at(monkeypatch, "127.0.0.1", _closed_port())
        runs, two_attempts = _counted_client_events(broker, until=2)
        lifespan = _app_lifespan()

        async with lifespan(FastAPI()):
            await asyncio.wait_for(two_attempts.wait(), ATTEMPTS_WITHIN_SECONDS)

            assert runs["startup"] == runs["shutdown"] == 2

    async def test_the_retry_stops_with_the_app(self, monkeypatch):
        _broker_pointed_at(monkeypatch, "127.0.0.1", _closed_port())
        lifespan = _app_lifespan()

        async with lifespan(FastAPI()):
            assert len(_retries_running()) == 1

        assert _retries_running() == []
