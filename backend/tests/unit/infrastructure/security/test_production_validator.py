"""Tests for production security validator."""

from unittest.mock import Mock

import pytest

from src.infrastructure.config.settings import EnvironmentOption, Settings
from src.infrastructure.security.production_validator import (
    ProductionSecurityError,
    ProductionSecurityValidator,
    validate_production_security,
)


class TestProductionSecurityValidator:
    """Test the production security validator."""

    def create_mock_settings(self, **overrides):
        """Create mock settings with defaults and overrides."""
        defaults = {
            "ENVIRONMENT": EnvironmentOption.PRODUCTION,
            "SECRET_KEY": "xF9mWqP3nL7vBfKsRt8HjZ2CyE5QaM6NuV4DgX1SpY7LwB9KzT3RhI0UoJ5PcA2MvS8",
            "POSTGRES_PASSWORD": "secure_db_password",
            "DATABASE_URL_OVERRIDE": None,
            "REDIS_PASSWORD": "secure_redis_password",
            "CACHE_BACKEND": "memcached",
            "RATE_LIMITER_BACKEND": "memcached",
            "SESSION_BACKEND": "redis",
            "CORS_ENABLED": True,
            "CORS_ORIGINS": "https://example.com",
            "DEBUG": False,
            "ENABLE_DOCS_IN_PRODUCTION": False,
            "SESSION_SECURE_COOKIES": True,
            "SESSION_TIMEOUT_MINUTES": 30,
            "CSRF_ENABLED": True,
            "ADMIN_ENABLED": True,
            "ADMIN_USERNAME": "secure_admin_user",
            "ADMIN_PASSWORD": "very_secure_admin_password_123",
            "PRODUCTION_SECURITY_VALIDATION_ENABLED": True,
            "PRODUCTION_SECURITY_STRICT_MODE": False,
            # Redis settings
            "CACHE_REDIS_HOST": "localhost",
            "CACHE_REDIS_PORT": 6379,
            "CACHE_REDIS_DB": 0,
            "CACHE_REDIS_PASSWORD": None,
            "RATE_LIMITER_REDIS_HOST": "localhost",
            "RATE_LIMITER_REDIS_PORT": 6379,
            "RATE_LIMITER_REDIS_DB": 1,
            "RATE_LIMITER_REDIS_PASSWORD": None,
        }
        defaults.update(overrides)

        # Create a mock settings object
        settings = Mock(spec=Settings)
        for key, value in defaults.items():
            setattr(settings, key, value)

        # Mock the property methods
        def get_cors_origins_list():
            origins = getattr(settings, "CORS_ORIGINS", "*")
            if not origins:
                return ["*"]
            return [x.strip() for x in origins.split(",") if x.strip()]

        # Add property methods
        settings.CORS_ORIGINS_LIST = get_cors_origins_list()

        return settings

    def test_non_production_environment_skips_validation(self):
        """Test that non-production environments skip validation."""
        settings = self.create_mock_settings(ENVIRONMENT=EnvironmentOption.DEVELOPMENT)
        validator = ProductionSecurityValidator(settings)

        # Should not raise any exceptions
        validator.validate_production_security()

    def test_secure_production_config_passes(self):
        """Test that a secure production configuration passes all checks."""
        settings = self.create_mock_settings()
        validator = ProductionSecurityValidator(settings)

        # Should not raise any exceptions
        validator.validate_production_security()

    def test_insecure_secret_key_raises_error(self):
        """Test that insecure SECRET_KEY raises critical error."""
        test_cases = [
            "insecure-secret-key-change-this",
            "change-me",
            "secret",
            "password",
            "123456",
            "short",  # Too short
            "",  # Empty
            "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",  # Repeated chars
            "abcd1234qwerty",  # Predictable patterns
        ]

        for insecure_key in test_cases:
            settings = self.create_mock_settings(SECRET_KEY=insecure_key)
            validator = ProductionSecurityValidator(settings)

            with pytest.raises(ProductionSecurityError) as exc_info:
                validator.validate_production_security()

            assert "SECRET_KEY" in str(exc_info.value)
            assert "insecure" in str(exc_info.value).lower()

    def test_admin_disabled_does_not_check_credentials(self):
        """Test that disabled admin doesn't trigger credential checks."""
        settings = self.create_mock_settings(ADMIN_ENABLED=False, ADMIN_USERNAME="admin", ADMIN_PASSWORD="weak")
        validator = ProductionSecurityValidator(settings)

        # Should not raise any exceptions for admin credentials
        validator.validate_production_security()

    def test_default_database_password_raises_error(self):
        """Test that default database password raises critical error."""
        settings = self.create_mock_settings(POSTGRES_PASSWORD="postgres")
        validator = ProductionSecurityValidator(settings)

        with pytest.raises(ProductionSecurityError) as exc_info:
            validator.validate_production_security()

        assert "Database" in str(exc_info.value)
        assert "default credentials" in str(exc_info.value)

    def test_empty_database_password_raises_error(self):
        """Test that empty database password raises critical error."""
        settings = self.create_mock_settings(POSTGRES_PASSWORD="")
        validator = ProductionSecurityValidator(settings)

        with pytest.raises(ProductionSecurityError) as exc_info:
            validator.validate_production_security()

        assert "Database password is empty" in str(exc_info.value)

    def test_database_url_password_overrides_postgres_password(self):
        """Test that credentials in DATABASE_URL are what gets validated.

        A managed provider (Neon, RDS, Cloud SQL) carries its credentials in
        DATABASE_URL while POSTGRES_PASSWORD keeps its default — that must not
        be reported as insecure.
        """
        settings = self.create_mock_settings(
            POSTGRES_PASSWORD="postgres",
            DATABASE_URL_OVERRIDE="postgresql+asyncpg://db_user:not_a_real_password@db.example.com:5432/app?ssl=require",
        )
        validator = ProductionSecurityValidator(settings)

        validator.validate_production_security()

    def test_default_password_in_database_url_raises_error(self):
        """Test that a default password inside DATABASE_URL is still caught."""
        settings = self.create_mock_settings(
            POSTGRES_PASSWORD="secure_db_password",
            DATABASE_URL_OVERRIDE="postgresql+asyncpg://postgres:postgres@db.example.com:5432/app",
        )
        validator = ProductionSecurityValidator(settings)

        with pytest.raises(ProductionSecurityError) as exc_info:
            validator.validate_production_security()

        assert "default credentials" in str(exc_info.value)

    def test_percent_encoded_password_in_database_url_is_decoded(self):
        """Test that a percent-encoded default password is decoded before checking."""
        settings = self.create_mock_settings(
            DATABASE_URL_OVERRIDE="postgresql+asyncpg://postgres:postgre%73@db.example.com:5432/app",
        )
        validator = ProductionSecurityValidator(settings)

        with pytest.raises(ProductionSecurityError) as exc_info:
            validator.validate_production_security()

        assert "default credentials" in str(exc_info.value)

    def test_database_url_without_password_warns_instead_of_failing(self, caplog):
        """Test that a passwordless DATABASE_URL warns but still starts.

        Authentication may be handled outside the connection string (IAM,
        client certificates, a trusted socket), which cannot be verified here.
        """
        settings = self.create_mock_settings(
            POSTGRES_PASSWORD="postgres",
            DATABASE_URL_OVERRIDE="postgresql+asyncpg://app_user@db.example.com:5432/app",
        )
        validator = ProductionSecurityValidator(settings)

        validator.validate_production_security()

        warning_logs = [record for record in caplog.records if record.levelname == "WARNING"]
        password_warnings = [log for log in warning_logs if "DATABASE_URL is set but contains no password" in log.message]
        assert len(password_warnings) > 0

    def test_multiple_critical_errors_combined(self):
        """Test that multiple critical errors are combined in one message."""
        settings = self.create_mock_settings(SECRET_KEY="insecure", POSTGRES_PASSWORD="postgres")
        validator = ProductionSecurityValidator(settings)

        with pytest.raises(ProductionSecurityError) as exc_info:
            validator.validate_production_security()

        error_msg = str(exc_info.value)
        assert "SECRET_KEY" in error_msg
        assert "Database" in error_msg

    def test_redis_without_password_logs_warning(self, caplog):
        """Test that Redis without password logs warning."""
        settings = self.create_mock_settings(CACHE_BACKEND="redis", CACHE_REDIS_PASSWORD=None)
        validator = ProductionSecurityValidator(settings)

        validator.validate_production_security()

        # Check that warnings were logged
        warning_logs = [record for record in caplog.records if record.levelname == "WARNING"]
        assert len(warning_logs) > 0

        # Check that Redis password warnings are present
        redis_warnings = [log for log in warning_logs if "Redis instance" in log.message and "no password" in log.message]
        assert len(redis_warnings) > 0

    def test_shared_redis_instance_logs_warning(self, caplog):
        """Test that shared Redis instances log warning."""
        settings = self.create_mock_settings(
            CACHE_BACKEND="redis",
            RATE_LIMITER_BACKEND="redis",
            # Both using same Redis instance
            CACHE_REDIS_HOST="localhost",
            CACHE_REDIS_PORT=6379,
            CACHE_REDIS_DB=0,
            RATE_LIMITER_REDIS_HOST="localhost",
            RATE_LIMITER_REDIS_PORT=6379,
            RATE_LIMITER_REDIS_DB=0,  # Same DB to test shared instance warning
        )
        validator = ProductionSecurityValidator(settings)

        validator.validate_production_security()

        # Check for shared instance warning
        warning_logs = [record for record in caplog.records if record.levelname == "WARNING"]
        shared_warnings = [log for log in warning_logs if "sharing the same Redis instance" in log.message]
        assert len(shared_warnings) > 0

    def test_permissive_cors_logs_warning(self, caplog):
        """Test that permissive CORS logs warning."""
        settings = self.create_mock_settings(CORS_ORIGINS="*")
        validator = ProductionSecurityValidator(settings)

        validator.validate_production_security()

        # Check for CORS warning
        warning_logs = [record for record in caplog.records if record.levelname == "WARNING"]
        cors_warnings = [log for log in warning_logs if "CORS_ORIGINS" in log.message and "allow all origins" in log.message]
        assert len(cors_warnings) > 0

    def test_debug_enabled_logs_warning(self, caplog):
        """Test that debug mode enabled logs warning."""
        settings = self.create_mock_settings(DEBUG=True)
        validator = ProductionSecurityValidator(settings)

        validator.validate_production_security()

        # Check for debug warning
        warning_logs = [record for record in caplog.records if record.levelname == "WARNING"]
        debug_warnings = [log for log in warning_logs if "DEBUG mode" in log.message]
        assert len(debug_warnings) > 0

    def test_docs_enabled_logs_warning(self, caplog):
        """Test that docs enabled in production logs warning."""
        settings = self.create_mock_settings(ENABLE_DOCS_IN_PRODUCTION=True)
        validator = ProductionSecurityValidator(settings)

        validator.validate_production_security()

        # Check for docs warning
        warning_logs = [record for record in caplog.records if record.levelname == "WARNING"]
        docs_warnings = [log for log in warning_logs if "API documentation" in log.message]
        assert len(docs_warnings) > 0

    def test_insecure_session_config_logs_warning(self, caplog):
        """Test that insecure session configuration logs warnings."""
        settings = self.create_mock_settings(
            SESSION_SECURE_COOKIES=False,
            SESSION_TIMEOUT_MINUTES=180,  # 3 hours
            CSRF_ENABLED=False,
        )
        validator = ProductionSecurityValidator(settings)

        validator.validate_production_security()

        # Check for session warnings
        warning_logs = [record for record in caplog.records if record.levelname == "WARNING"]

        cookie_warnings = [log for log in warning_logs if "SESSION_SECURE_COOKIES" in log.message]
        timeout_warnings = [log for log in warning_logs if "Session timeout" in log.message]
        csrf_warnings = [log for log in warning_logs if "CSRF protection" in log.message]

        assert len(cookie_warnings) > 0
        assert len(timeout_warnings) > 0
        assert len(csrf_warnings) > 0

    def test_weak_admin_credentials_logs_warning(self, caplog):
        """Test that weak admin credentials log warnings."""
        settings = self.create_mock_settings(ADMIN_USERNAME="admin", ADMIN_PASSWORD="123456")
        validator = ProductionSecurityValidator(settings)

        validator.validate_production_security()

        # Check for admin credential warnings
        warning_logs = [record for record in caplog.records if record.levelname == "WARNING"]

        username_warnings = [log for log in warning_logs if "Admin username" in log.message and "predictable" in log.message]
        password_warnings = [log for log in warning_logs if "Admin password" in log.message]

        assert len(username_warnings) > 0
        assert len(password_warnings) > 0

    def test_convenience_function(self):
        """Test the convenience function validate_production_security."""
        settings = self.create_mock_settings(SECRET_KEY="insecure")

        with pytest.raises(ProductionSecurityError):
            validate_production_security(settings)

    def test_no_admin_credentials_skips_admin_checks(self, caplog):
        """Test that missing admin credentials skip admin checks."""
        settings = self.create_mock_settings(ADMIN_USERNAME="", ADMIN_PASSWORD="")
        validator = ProductionSecurityValidator(settings)

        validator.validate_production_security()

        # Should not have admin credential warnings
        warning_logs = [record for record in caplog.records if record.levelname == "WARNING"]
        admin_warnings = [log for log in warning_logs if "Admin username" in log.message or "Admin password" in log.message]
        assert len(admin_warnings) == 0

    def test_redis_ssl_with_external_host(self, caplog):
        """Test that external Redis without SSL logs warning."""
        settings = self.create_mock_settings(
            CACHE_BACKEND="redis",
            CACHE_REDIS_HOST="redis.example.com",  # External host
        )
        validator = ProductionSecurityValidator(settings)

        validator.validate_production_security()

        # Check for SSL warnings
        warning_logs = [record for record in caplog.records if record.levelname == "WARNING"]
        ssl_warnings = [log for log in warning_logs if "not using SSL/TLS" in log.message]
        assert len(ssl_warnings) > 0

    def test_localhost_redis_no_ssl_warning(self, caplog):
        """Test that localhost Redis without SSL doesn't log SSL warning."""
        settings = self.create_mock_settings(CACHE_BACKEND="redis", CACHE_REDIS_HOST="localhost")
        validator = ProductionSecurityValidator(settings)

        validator.validate_production_security()

        # Should not have SSL warnings for localhost
        warning_logs = [record for record in caplog.records if record.levelname == "WARNING"]
        ssl_warnings = [log for log in warning_logs if "not using SSL/TLS" in log.message]
        assert len(ssl_warnings) == 0
