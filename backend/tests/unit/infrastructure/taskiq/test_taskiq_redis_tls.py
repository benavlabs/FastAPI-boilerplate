"""The broker's Redis speaks TLS when ``TASKIQ_REDIS_SSL`` says so."""

import pytest

from src.infrastructure.taskiq.settings import TaskiqSettings
from tests.fixtures.redis_tls import connection_in_a_fresh_process, spoken


@pytest.mark.parametrize(("ssl", "scheme"), [(True, "rediss://"), (False, "redis://")])
def test_the_broker_url_speaks_tls_when_asked(ssl: bool, scheme: str):
    assert TaskiqSettings(TASKIQ_BROKER_TYPE="redis", TASKIQ_REDIS_SSL=ssl).TASKIQ_BROKER_URL.startswith(scheme)


@pytest.mark.parametrize("ssl", [True, False])
def test_the_broker_and_its_result_backend_speak_tls_when_the_setting_says(ssl: bool):
    shown = connection_in_a_fresh_process(
        {"TASKIQ_BROKER_TYPE": "redis", "TASKIQ_REDIS_SSL": str(ssl).lower()},
        "from src.infrastructure.taskiq.brokers import default_broker as broker",
        "broker.connection_pool.connection_class.__name__, "
        "'rediss' if broker.result_backend.redis_pool.connection_class.__name__ == 'SSLConnection' else 'redis'",
    )

    assert shown == spoken(ssl)
