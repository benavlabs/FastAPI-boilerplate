"""The broker the app builds, and the format it stores results in."""

import inspect
import json
import pickle
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any, NamedTuple

import pytest
from aio_pika import connect_robust
from pydantic_core import PydanticSerializationError
from taskiq.result import TaskiqResult
from taskiq.serializers import JSONSerializer
from taskiq_aio_pika import AioPikaBroker
from taskiq_redis import ListQueueBroker, RedisAsyncResultBackend, redis_backend

from src.infrastructure.config.enums import TaskiqBrokerType
from src.infrastructure.taskiq import brokers
from src.infrastructure.taskiq.brokers import create_default_broker
from src.infrastructure.taskiq.constants import BROKER_CONNECT_SECONDS, RESULT_KEPT_SECONDS


def _result_backend() -> RedisAsyncResultBackend:
    backend = create_default_broker().result_backend
    assert isinstance(backend, RedisAsyncResultBackend)

    return backend


def _result(return_value: Any) -> TaskiqResult:
    return TaskiqResult(is_err=False, return_value=return_value, execution_time=0.1)


class _Written(NamedTuple):
    """What the backend wrote to Redis: the value under each key, and how it was set."""

    store: dict[str, bytes]
    options: dict[str, dict[str, Any]]


@pytest.fixture
def written(monkeypatch) -> Iterator[_Written]:
    """Keep what the backend writes to Redis, values and set options alike."""
    kept = _Written(store={}, options={})

    class _Redis:
        def __init__(self, connection_pool: Any = None) -> None:
            pass

        async def __aenter__(self) -> "_Redis":
            return self

        async def __aexit__(self, *details: Any) -> bool:
            return False

        async def set(self, name: str, value: bytes, **options: Any) -> None:
            kept.store[name] = value
            kept.options[name] = options

        async def get(self, name: str) -> bytes | None:
            return kept.store.get(name)

    monkeypatch.setattr(redis_backend, "Redis", _Redis)

    yield kept


class TestTheRedisResultBackend:
    """Results are written and read as JSON."""

    def test_it_serializes_with_json(self):
        serializer = _result_backend().serializer

        assert isinstance(serializer, JSONSerializer)

    async def test_a_result_round_trips(self, written: _Written):
        backend = _result_backend()

        await backend.set_result("task-1", _result({"widgets": 3}))

        assert json.loads(next(iter(written.store.values())))["return_value"] == {"widgets": 3}
        assert (await backend.get_result("task-1")).return_value == {"widgets": 3}

    async def test_a_datetime_comes_back_as_an_iso_string(self, written: _Written):
        backend = _result_backend()

        await backend.set_result("task-2", _result(datetime(2026, 10, 1, 12, 30, tzinfo=UTC)))

        assert (await backend.get_result("task-2")).return_value == "2026-10-01T12:30:00Z"

    async def test_a_value_json_has_no_form_for_is_refused(self, written: _Written):
        class Row:
            id = 1

        with pytest.raises(PydanticSerializationError):
            await _result_backend().set_result("task-3", _result(Row()))

    async def test_a_result_is_written_with_an_expiry(self, written: _Written):
        """A result nothing came back for would otherwise be kept in Redis for good."""
        await _result_backend().set_result("task-5", _result("done"))

        assert list(written.options.values()) == [{"ex": RESULT_KEPT_SECONDS}]

    async def test_a_pickle_written_to_the_result_key_is_refused(self, written: _Written):
        backend = _result_backend()
        await backend.set_result("task-4", _result("fine"))
        key = next(iter(written.store))
        written.store[key] = pickle.dumps({"is_err": False, "return_value": "chosen", "execution_time": 0.1})

        with pytest.raises(UnicodeDecodeError):
            await backend.get_result("task-4")


class TestTheBrokerTheProjectBuilds:
    """What the factory passes has to be what the broker takes."""

    def test_the_rabbitmq_broker_passes_the_connect_timeout_and_nothing_else_to_the_connection(self, monkeypatch):
        """A keyword ``AioPikaBroker`` doesn't declare is forwarded to the AMQP connection instead.

        Nested under a ``connection_kwargs`` key of its own, the timeout reaches
        ``connect_robust`` as an argument it ignores, and the attempt stays unbounded.
        """
        monkeypatch.setattr(brokers.settings, "TASKIQ_BROKER_TYPE", TaskiqBrokerType.RABBITMQ.value)

        broker = create_default_broker()

        assert isinstance(broker, AioPikaBroker)
        assert broker._conn_kwargs == {"timeout": BROKER_CONNECT_SECONDS}
        assert "timeout" in inspect.signature(connect_robust).parameters

    def test_the_redis_broker_publishes_to_the_queue_it_is_given(self):
        broker = create_default_broker()

        assert isinstance(broker, ListQueueBroker)
        assert broker.queue_name == "default"

    def test_the_redis_broker_bounds_how_long_it_waits_to_connect(self):
        """redis-py leaves it unset, so a host that does not answer holds the caller for good."""
        broker = create_default_broker()

        assert isinstance(broker, ListQueueBroker)
        assert broker.connection_pool.connection_kwargs["socket_connect_timeout"] == BROKER_CONNECT_SECONDS

    def test_the_redis_broker_leaves_reading_unbounded(self):
        """The worker waits for its next job in a ``brpop`` that has no timeout of its own.

        A socket that stops waiting raises ``redis.exceptions.TimeoutError`` out of the
        listener the first time the queue is idle that long, and that loop catches the
        built-in ``ConnectionError``, which no redis exception inherits. A caller that
        needs a bound on a stalled broker puts it around its own call.
        """
        broker = create_default_broker()

        assert isinstance(broker, ListQueueBroker)
        assert "socket_timeout" not in broker.connection_pool.connection_kwargs
