"""The broker URL this feature builds from configuration."""

import pytest
from sqlalchemy.engine import make_url

from src.infrastructure.taskiq.settings import TaskiqSettings

AWKWARD = "p@ss/word#1:x%"


@pytest.mark.parametrize("broker", ["redis", "rabbitmq"])
def test_the_broker_password_survives_the_url(broker: str):
    settings = TaskiqSettings(
        TASKIQ_BROKER_TYPE=broker,
        TASKIQ_REDIS_PASSWORD=AWKWARD,
        TASKIQ_RABBITMQ_PASSWORD=AWKWARD,
    )

    assert make_url(settings.TASKIQ_BROKER_URL).password == AWKWARD
