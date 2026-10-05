"""The broker the app builds, and the format it stores results in."""

import json
import pickle
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic_core import PydanticSerializationError
from taskiq.result import TaskiqResult
from taskiq.serializers import JSONSerializer
from taskiq_aio_pika import AioPikaBroker
from taskiq_redis import ListQueueBroker, RedisAsyncResultBackend, redis_backend

from src.infrastructure.config.enums import TaskiqBrokerType
from src.infrastructure.taskiq import brokers
from src.infrastructure.taskiq.brokers import create_default_broker


def _result_backend() -> RedisAsyncResultBackend:
    backend = create_default_broker().result_backend
    assert isinstance(backend, RedisAsyncResultBackend)

    return backend


def _result(return_value: Any) -> TaskiqResult:
    return TaskiqResult(is_err=False, return_value=return_value, execution_time=0.1)


@pytest.fixture
def written(monkeypatch) -> Iterator[dict[str, bytes]]:
    """Keep what the backend writes to Redis in a dict."""
    store: dict[str, bytes] = {}

    class _Redis:
        def __init__(self, connection_pool: Any = None) -> None:
            pass

        async def __aenter__(self) -> "_Redis":
            return self

        async def __aexit__(self, *details: Any) -> bool:
            return False

        async def set(self, name: str, value: bytes, **options: Any) -> None:
            store[name] = value

        async def get(self, name: str) -> bytes | None:
            return store.get(name)

    monkeypatch.setattr(redis_backend, "Redis", _Redis)

    yield store


class TestTheRedisResultBackend:
    """Results are written and read as JSON."""

    def test_it_serializes_with_json(self):
        serializer = _result_backend().serializer

        assert isinstance(serializer, JSONSerializer)

    async def test_a_result_round_trips(self, written: dict[str, bytes]):
        backend = _result_backend()

        await backend.set_result("task-1", _result({"widgets": 3}))

        assert json.loads(next(iter(written.values())))["return_value"] == {"widgets": 3}
        assert (await backend.get_result("task-1")).return_value == {"widgets": 3}

    async def test_a_datetime_comes_back_as_an_iso_string(self, written: dict[str, bytes]):
        backend = _result_backend()

        await backend.set_result("task-2", _result(datetime(2026, 10, 1, 12, 30, tzinfo=UTC)))

        assert (await backend.get_result("task-2")).return_value == "2026-10-01T12:30:00Z"

    async def test_a_value_json_has_no_form_for_is_refused(self, written: dict[str, bytes]):
        class Row:
            id = 1

        with pytest.raises(PydanticSerializationError):
            await _result_backend().set_result("task-3", _result(Row()))

    async def test_a_pickle_written_to_the_result_key_is_refused(self, written: dict[str, bytes]):
        backend = _result_backend()
        await backend.set_result("task-4", _result("fine"))
        key = next(iter(written))
        written[key] = pickle.dumps({"is_err": False, "return_value": "chosen", "execution_time": 0.1})

        with pytest.raises(UnicodeDecodeError):
            await backend.get_result("task-4")


class TestTheBrokerTheProjectBuilds:
    """What the factory passes has to be what the broker takes."""

    def test_the_rabbitmq_broker_gets_no_argument_the_library_does_not_declare(self, monkeypatch):
        """A keyword ``AioPikaBroker`` doesn't declare is forwarded to the AMQP connection instead."""
        monkeypatch.setattr(brokers.settings, "TASKIQ_BROKER_TYPE", TaskiqBrokerType.RABBITMQ.value)

        broker = create_default_broker()

        assert isinstance(broker, AioPikaBroker)
        assert broker._conn_kwargs == {}

    def test_the_redis_broker_publishes_to_the_queue_it_is_given(self):
        broker = create_default_broker()

        assert isinstance(broker, ListQueueBroker)
        assert broker.queue_name == "default"
