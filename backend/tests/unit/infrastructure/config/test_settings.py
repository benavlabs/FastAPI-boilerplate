"""Tests for configuration settings."""

import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from src.infrastructure.config.settings import EnvironmentOption, Settings, get_settings

_MOUNTED_PATHS = """
from src.interfaces.api import router

print("PATHS:" + ",".join(route.path for route in router.routes))
"""


def _mounted_api_paths(**environment: str) -> list[str]:
    """The paths the API router mounts, read from a cold interpreter."""
    result = subprocess.run(
        [sys.executable, "-c", _MOUNTED_PATHS],
        cwd=Path(__file__).resolve().parents[4],
        capture_output=True,
        text=True,
        check=True,
        env={**os.environ, **environment},
    )
    line = next(line for line in result.stdout.splitlines() if line.startswith("PATHS:"))

    return [path for path in line.removeprefix("PATHS:").split(",") if path]


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


class TestCORSSettings:
    """Credentialed requests reject a wildcard origin, so the default must not be one."""

    def test_the_default_origins_are_explicit_not_a_wildcard(self):
        origins = Settings().CORS_ORIGINS_LIST

        assert origins
        assert "*" not in origins
        assert all(origin.startswith("http") for origin in origins)

    @patch.dict(os.environ, {"CORS_ORIGINS": "http://a.test, http://b.test ,"})
    def test_the_origin_list_strips_whitespace_and_drops_empties(self):
        assert Settings().CORS_ORIGINS_LIST == ["http://a.test", "http://b.test"]


def test_the_environment_setting_only_takes_values_it_can_hold():
    """``ENVIRONMENT=pytest`` used to be read as a signal here and then fail the cast."""
    assert {option.value for option in EnvironmentOption} == {"production", "staging", "development", "local"}

    with pytest.raises(ValueError):
        EnvironmentOption("pytest")


class TestSettingsNothingReads:
    """Settings that promised behaviour the code never had are gone."""

    @pytest.mark.parametrize(
        "name",
        [
            "LOG_CORRELATION_ID",
            "LOG_INCLUDE_STACKTRACE",
            "LOG_PERFORMANCE_METRICS",
            "LOG_SQL_QUERIES",
            "LOG_STRUCTURED_CONTEXT",
            "DEFAULT_CACHE_EXPIRATION",
            "POSTGRES_SYNC_PREFIX",
            "PRODUCTION_SECURITY_STRICT_MODE",
        ],
    )
    def test_the_setting_is_gone(self, name: str):
        assert not hasattr(get_settings(), name), name

    def test_every_api_route_sits_under_the_configured_prefix(self):
        assert [path for path in _mounted_api_paths() if not path.startswith(get_settings().API_PREFIX)] == []

    def test_a_configured_prefix_moves_the_api(self):
        """The prefix used to be hard-coded in the router, so setting it did nothing."""
        moved = _mounted_api_paths(API_PREFIX="/service")

        assert [path for path in moved if not path.startswith("/service")] == []
