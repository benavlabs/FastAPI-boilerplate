"""Tests for configuration settings."""

import os
from unittest.mock import patch

import pytest

from src.infrastructure.config.settings import EnvironmentOption, Settings, get_settings


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
