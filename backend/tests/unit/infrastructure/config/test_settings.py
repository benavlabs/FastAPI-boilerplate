"""Tests for configuration settings."""

import os
from unittest.mock import patch

import pytest

from src.infrastructure.config.settings import Settings, get_settings


class TestSettings:
    """Test cases for application settings."""

    def test_settings_creation(self):
        """Test creating settings instance."""
        settings = Settings()
        assert settings is not None
        assert hasattr(settings, "DATABASE_URL")
        assert hasattr(settings, "SECRET_KEY")

    def test_get_settings_singleton(self):
        """Test that get_settings returns the same instance."""
        settings1 = get_settings()
        settings2 = get_settings()
        assert settings1 is settings2

    @patch.dict(os.environ, {"SECRET_KEY": "test_secret_key"})
    def test_settings_from_env(self):
        """Test loading settings from environment variables."""
        settings = Settings()
        assert settings.SECRET_KEY == "test_secret_key"

    def test_database_url_format(self):
        """Test database URL format validation."""
        settings = get_settings()
        assert settings.DATABASE_URL is not None
        # Should be a valid database URL format
        assert "://" in settings.DATABASE_URL

    @patch.dict(
        os.environ, {"DATABASE_URL": "postgresql+asyncpg://prod_user:prod_pass@prod.example.com:5432/prod_db"}, clear=False
    )
    def test_database_url_env_var_override(self):
        """Test that DATABASE_URL environment variable takes precedence."""
        settings = Settings()
        expected_url = "postgresql+asyncpg://prod_user:prod_pass@prod.example.com:5432/prod_db"
        assert settings.DATABASE_URL == expected_url

    @patch.dict(os.environ, {}, clear=False)
    def test_database_url_fallback_to_constructed(self):
        """Test that DATABASE_URL falls back to constructed URL when env var not set."""
        # Remove DATABASE_URL if it exists
        if "DATABASE_URL" in os.environ:
            del os.environ["DATABASE_URL"]

        settings = Settings()
        # Should construct URL from components
        assert "postgresql+asyncpg://" in settings.DATABASE_URL
        assert "postgres:postgres@localhost:5432" in settings.DATABASE_URL

    @patch.dict(os.environ, {"DEBUG": "true"})
    def test_debug_mode_setting(self):
        """Test debug mode configuration."""
        settings = Settings()
        # Assuming DEBUG is a boolean setting
        if hasattr(settings, "DEBUG"):
            assert isinstance(settings.DEBUG, bool)

    def test_required_settings_exist(self):
        """Test that all required settings are present."""
        settings = get_settings()

        # Core required settings
        required_attrs = [
            "DATABASE_URL",
            "SECRET_KEY",
        ]

        for attr in required_attrs:
            assert hasattr(settings, attr), f"Missing required setting: {attr}"
            assert getattr(settings, attr) is not None, f"Setting {attr} is None"

    @patch.dict(os.environ, {"SQLITE_URI": ":memory:"})
    def test_test_database_override(self):
        """Test that test database settings work."""
        settings = Settings()
        # In test mode, should use in-memory database
        if hasattr(settings, "SQLITE_URI"):
            assert ":memory:" in settings.SQLITE_URI


class TestSessionSettings:
    """Test cases for session storage settings."""

    def test_session_redis_settings_defaults(self):
        """Session Redis settings default to localhost on a DB no other service uses."""
        settings = Settings()

        assert settings.SESSION_REDIS_HOST == "localhost"
        assert settings.SESSION_REDIS_PORT == 6379
        assert settings.SESSION_REDIS_DB == 2
        assert settings.SESSION_REDIS_PASSWORD is None
        other_dbs = {settings.CACHE_REDIS_DB, settings.RATE_LIMITER_REDIS_DB, settings.TASKIQ_REDIS_DB}
        assert settings.SESSION_REDIS_DB not in other_dbs

    @patch.dict(
        os.environ,
        {
            "SESSION_REDIS_HOST": "sessions-redis",
            "SESSION_REDIS_PORT": "6380",
            "SESSION_REDIS_DB": "7",
            "SESSION_REDIS_PASSWORD": "test-password",
        },
    )
    def test_session_redis_settings_from_env(self):
        """Session Redis settings can be overridden independently of the cache."""
        settings = Settings()

        assert settings.SESSION_REDIS_HOST == "sessions-redis"
        assert settings.SESSION_REDIS_PORT == 6380
        assert settings.SESSION_REDIS_DB == 7
        assert settings.SESSION_REDIS_PASSWORD == "test-password"

    def test_session_redis_url_without_password(self):
        """SESSION_REDIS_URL is built from the session settings."""
        settings = Settings()

        assert settings.SESSION_REDIS_URL == "redis://localhost:6379/2"

    @patch.dict(
        os.environ,
        {"SESSION_REDIS_HOST": "redis-host", "SESSION_REDIS_PORT": "6380", "SESSION_REDIS_PASSWORD": "p@ss/word"},
    )
    def test_session_redis_url_with_password(self):
        """The password is URL-encoded so reserved characters don't break the URL."""
        settings = Settings()

        assert settings.SESSION_REDIS_URL == "redis://:p%40ss%2Fword@redis-host:6380/2"


class TestTaskiqSettings:
    """Test cases for Taskiq configuration settings."""

    def test_taskiq_settings_defaults(self):
        """Test Taskiq settings have correct defaults."""
        settings = get_settings()

        # Test default values
        assert settings.TASKIQ_ENABLED is True
        assert settings.TASKIQ_BROKER_TYPE == "redis"
        assert settings.TASKIQ_REDIS_HOST == "localhost"
        assert settings.TASKIQ_REDIS_PORT == 6379
        assert settings.TASKIQ_REDIS_DB == 3
        assert settings.TASKIQ_REDIS_PASSWORD is None
        assert settings.TASKIQ_WORKER_CONCURRENCY == 2
        assert settings.TASKIQ_MAX_TASKS_PER_WORKER == 1000

    @patch.dict(
        os.environ,
        {
            "TASKIQ_ENABLED": "false",
            "TASKIQ_BROKER_TYPE": "rabbitmq",
            "TASKIQ_REDIS_HOST": "redis-server",
            "TASKIQ_REDIS_PORT": "6380",
            "TASKIQ_REDIS_DB": "5",
            "TASKIQ_REDIS_PASSWORD": "test-password",
            "TASKIQ_WORKER_CONCURRENCY": "4",
            "TASKIQ_MAX_TASKS_PER_WORKER": "500",
        },
    )
    def test_taskiq_settings_from_env(self):
        """Test loading Taskiq settings from environment variables."""
        settings = Settings()

        assert settings.TASKIQ_ENABLED is False
        assert settings.TASKIQ_BROKER_TYPE == "rabbitmq"
        assert settings.TASKIQ_REDIS_HOST == "redis-server"
        assert settings.TASKIQ_REDIS_PORT == 6380
        assert settings.TASKIQ_REDIS_DB == 5
        assert settings.TASKIQ_REDIS_PASSWORD == "test-password"
        assert settings.TASKIQ_WORKER_CONCURRENCY == 4
        assert settings.TASKIQ_MAX_TASKS_PER_WORKER == 500

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
            "TASKIQ_ENABLED",
            "TASKIQ_BROKER_TYPE",
            "TASKIQ_REDIS_HOST",
            "TASKIQ_REDIS_PORT",
            "TASKIQ_REDIS_DB",
            "TASKIQ_RABBITMQ_HOST",
            "TASKIQ_RABBITMQ_PORT",
            "TASKIQ_RABBITMQ_USER",
            "TASKIQ_RABBITMQ_PASSWORD",
            "TASKIQ_RABBITMQ_VHOST",
            "TASKIQ_WORKER_CONCURRENCY",
            "TASKIQ_MAX_TASKS_PER_WORKER",
            "TASKIQ_BROKER_URL",
        ]

        for attr in required_attrs:
            assert hasattr(settings, attr), f"Missing required Taskiq setting: {attr}"
