"""The broker settings the taskiq feature contributes."""

import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from yarl import URL

from src.infrastructure.config.settings import Settings, get_settings
from src.infrastructure.taskiq.settings import TaskiqSettings

BACKEND = Path(__file__).resolve().parents[4]
RETRY_COUNT = "TASKIQ_DEFAULT_RETRY_COUNT"

_DECLARED_DEFAULT = f"""
from src.infrastructure.taskiq.settings import TaskiqSettings

print("DEFAULT:" + str(TaskiqSettings.model_fields["{RETRY_COUNT}"].default))
"""


def _declared_retry_count() -> int:
    """The declared default, read in an interpreter whose environment doesn't set it."""
    child = {name: value for name, value in os.environ.items() if name != RETRY_COUNT}
    result = subprocess.run(
        [sys.executable, "-c", _DECLARED_DEFAULT], cwd=BACKEND, capture_output=True, text=True, check=True, env=child
    )
    line = next(line for line in result.stdout.splitlines() if line.startswith("DEFAULT:"))

    return int(line.removeprefix("DEFAULT:"))


def test_a_task_is_retried_three_times_unless_the_environment_says_otherwise():
    assert _declared_retry_count() == 3


@patch.dict(os.environ, {RETRY_COUNT: "0"})
def test_the_retry_count_comes_from_the_environment():
    assert TaskiqSettings().TASKIQ_DEFAULT_RETRY_COUNT == 0


class TestTaskiqSettings:
    """Test cases for Taskiq configuration settings."""

    def test_taskiq_settings_defaults(self):
        """Test Taskiq settings have correct defaults."""
        settings = get_settings()

        # Test default values
        assert settings.TASKIQ_BROKER_TYPE == "redis"
        assert settings.TASKIQ_REDIS_HOST == "localhost"
        assert settings.TASKIQ_REDIS_PORT == 6379
        assert settings.TASKIQ_REDIS_DB == 3
        assert settings.TASKIQ_REDIS_PASSWORD is None

    @patch.dict(
        os.environ,
        {
            "TASKIQ_BROKER_TYPE": "rabbitmq",
            "TASKIQ_REDIS_HOST": "redis-server",
            "TASKIQ_REDIS_PORT": "6380",
            "TASKIQ_REDIS_DB": "5",
            "TASKIQ_REDIS_PASSWORD": "test-password",
        },
    )
    def test_taskiq_settings_from_env(self):
        """Test loading Taskiq settings from environment variables."""
        settings = Settings()

        assert settings.TASKIQ_BROKER_TYPE == "rabbitmq"
        assert settings.TASKIQ_REDIS_HOST == "redis-server"
        assert settings.TASKIQ_REDIS_PORT == 6380
        assert settings.TASKIQ_REDIS_DB == 5
        assert settings.TASKIQ_REDIS_PASSWORD == "test-password"

    @patch.dict(
        os.environ,
        {
            "TASKIQ_RABBITMQ_HOST": "rabbitmq-server",
            "TASKIQ_RABBITMQ_PORT": "5673",
            "TASKIQ_RABBITMQ_USER": "test-user",
            "TASKIQ_RABBITMQ_PASSWORD": "test-password",
            "TASKIQ_RABBITMQ_VHOST": "/test",
        },
    )
    def test_taskiq_rabbitmq_settings_from_env(self):
        """Test loading Taskiq RabbitMQ settings from environment variables."""
        settings = Settings()

        assert settings.TASKIQ_RABBITMQ_HOST == "rabbitmq-server"
        assert settings.TASKIQ_RABBITMQ_PORT == 5673
        assert settings.TASKIQ_RABBITMQ_USER == "test-user"
        assert settings.TASKIQ_RABBITMQ_PASSWORD == "test-password"
        assert settings.TASKIQ_RABBITMQ_VHOST == "/test"

    def test_taskiq_redis_broker_url_generation(self):
        """Test Redis broker URL generation."""
        settings = get_settings()

        # Test Redis URL without password
        broker_url = settings.TASKIQ_BROKER_URL
        expected_url = f"redis://{settings.TASKIQ_REDIS_HOST}:{settings.TASKIQ_REDIS_PORT}/{settings.TASKIQ_REDIS_DB}"
        assert broker_url == expected_url

    @patch.dict(
        os.environ,
        {
            "TASKIQ_REDIS_PASSWORD": "test-password",
            "TASKIQ_REDIS_HOST": "redis-host",
            "TASKIQ_REDIS_PORT": "6380",
            "TASKIQ_REDIS_DB": "2",
        },
    )
    def test_taskiq_redis_broker_url_with_password(self):
        """Test Redis broker URL generation with password."""
        settings = Settings()

        broker_url = settings.TASKIQ_BROKER_URL
        expected_url = "redis://:test-password@redis-host:6380/2"
        assert broker_url == expected_url

    @patch.dict(
        os.environ,
        {
            "TASKIQ_BROKER_TYPE": "rabbitmq",
            "TASKIQ_RABBITMQ_USER": "test-user",
            "TASKIQ_RABBITMQ_PASSWORD": "test-password",
            "TASKIQ_RABBITMQ_HOST": "rabbitmq-host",
            "TASKIQ_RABBITMQ_PORT": "5673",
            "TASKIQ_RABBITMQ_VHOST": "/test",
        },
    )
    def test_taskiq_rabbitmq_broker_url_generation(self):
        """Test RabbitMQ broker URL generation."""
        settings = Settings()

        broker_url = settings.TASKIQ_BROKER_URL
        expected_url = "amqp://test-user:test-password@rabbitmq-host:5673/test"
        assert broker_url == expected_url

    @patch.dict(os.environ, {"TASKIQ_BROKER_TYPE": "invalid"})
    def test_taskiq_invalid_broker_type_raises_error(self):
        """Test that invalid broker type raises ValueError."""
        settings = Settings()

        with pytest.raises(ValueError, match="Unsupported broker type: invalid"):
            settings.TASKIQ_BROKER_URL

    def test_taskiq_required_settings_exist(self):
        """Test that all required Taskiq settings are present."""
        settings = get_settings()

        required_attrs = [
            "TASKIQ_BROKER_TYPE",
            "TASKIQ_REDIS_HOST",
            "TASKIQ_REDIS_PORT",
            "TASKIQ_REDIS_DB",
            "TASKIQ_RABBITMQ_HOST",
            "TASKIQ_RABBITMQ_PORT",
            "TASKIQ_RABBITMQ_USER",
            "TASKIQ_RABBITMQ_PASSWORD",
            "TASKIQ_RABBITMQ_VHOST",
            "TASKIQ_BROKER_URL",
        ]

        for attr in required_attrs:
            assert hasattr(settings, attr), f"Missing required Taskiq setting: {attr}"


class TestTheBrokerUrlEscaping:
    """A vhost or password with punctuation in it still has to parse."""

    @patch.dict(
        os.environ,
        {
            "TASKIQ_BROKER_TYPE": "rabbitmq",
            "TASKIQ_RABBITMQ_USER": "user",
            "TASKIQ_RABBITMQ_PASSWORD": "p@ss/word",
            "TASKIQ_RABBITMQ_HOST": "rabbitmq",
            "TASKIQ_RABBITMQ_PORT": "5672",
            "TASKIQ_RABBITMQ_VHOST": "/tenant/one",
        },
    )
    def test_the_vhost_and_password_survive_the_url(self):
        url = URL(Settings().TASKIQ_BROKER_URL)

        assert url.path == "/tenant/one"
        assert url.password == "p@ss/word"


def test_the_workers_own_knobs_are_gone():
    """Nothing read them: the worker's concurrency is set on its command line."""
    settings = get_settings()

    for name in ("TASKIQ_WORKER_CONCURRENCY", "TASKIQ_MAX_TASKS_PER_WORKER"):
        assert not hasattr(settings, name), name
