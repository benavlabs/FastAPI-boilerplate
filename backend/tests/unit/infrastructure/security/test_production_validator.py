"""Tests for production security validator."""

import base64
import random
import secrets
from typing import cast
from unittest.mock import Mock

import pytest

from src.infrastructure.config.base import CoreSettings
from src.infrastructure.config.settings import EnvironmentOption, Settings
from src.infrastructure.security.production_validator import (
    ProductionSecurityError,
    ProductionSecurityValidator,
    validate_production_security,
)
from src.infrastructure.security.secret_key import is_weak_secret_key


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
            "RATE_LIMITER_ENABLED": False,
            "SESSION_BACKEND": "redis",
            "CORS_ENABLED": True,
            "CORS_ORIGINS": "https://example.com",
            "CORS_ALLOW_CREDENTIALS": False,
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
            "SESSION_REDIS_URL": "redis://localhost:6379/2",
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
            "my-company-api-signing-key-for-prod",  # Written by hand
            "0123456789abcdef" * 2,  # One block, twice
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
            RATE_LIMITER_ENABLED=True,
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

    def test_sessions_on_own_redis_db_do_not_warn_about_sharing(self, caplog):
        """Sessions on their own Redis DB are not reported as sharing the cache database."""
        settings = self.create_mock_settings(
            CACHE_BACKEND="redis", CACHE_REDIS_DB=0, SESSION_REDIS_URL="redis://localhost:6379/2"
        )
        validator = ProductionSecurityValidator(settings)

        validator.validate_production_security()

        shared_warnings = [record for record in caplog.records if "sharing the same Redis instance" in record.message]
        assert shared_warnings == []

    def test_sessions_sharing_cache_redis_db_logs_warning(self, caplog):
        """A session URL pointing at the cache database is reported as sharing."""
        settings = self.create_mock_settings(
            CACHE_BACKEND="redis", CACHE_REDIS_DB=0, SESSION_REDIS_URL="redis://localhost:6379/0"
        )
        validator = ProductionSecurityValidator(settings)

        validator.validate_production_security()

        shared_warnings = [record for record in caplog.records if "sharing the same Redis instance" in record.message]
        assert len(shared_warnings) == 1
        assert "cache, sessions" in shared_warnings[0].message

    def test_sessions_on_separate_redis_host_do_not_warn_about_sharing(self, caplog):
        """Same DB number on a different session Redis host is a different instance, not sharing."""
        settings = self.create_mock_settings(
            CACHE_BACKEND="redis", CACHE_REDIS_DB=0, SESSION_REDIS_URL="redis://sessions-redis:6379/0"
        )
        validator = ProductionSecurityValidator(settings)

        validator.validate_production_security()

        shared_warnings = [record for record in caplog.records if "sharing the same Redis instance" in record.message]
        assert shared_warnings == []

    def test_session_redis_url_with_tls_and_password_passes_redis_checks(self, caplog):
        """A rediss:// session URL with credentials satisfies the password and TLS checks."""
        settings = self.create_mock_settings(SESSION_REDIS_URL="rediss://default:p%40ss@sessions.example.com:6380/0")
        validator = ProductionSecurityValidator(settings)

        assert validator._get_redis_configurations() == [
            {
                "service": "sessions",
                "host": "sessions.example.com",
                "port": 6380,
                "db": 0,
                "password": "p@ss",
                "ssl": True,
            }
        ]

        validator.validate_production_security()

        session_warnings = [record for record in caplog.records if "Redis instance for sessions" in record.message]
        assert session_warnings == []

    @pytest.mark.parametrize(("allow_credentials", "expect_note"), [(True, True), (False, False)])
    def test_cors_wildcard_raises_error(self, allow_credentials, expect_note):
        """Test that CORS_ORIGINS='*' is a critical error, noting credentials when they are allowed."""
        settings = self.create_mock_settings(CORS_ORIGINS="*", CORS_ALLOW_CREDENTIALS=allow_credentials)
        validator = ProductionSecurityValidator(settings)

        with pytest.raises(ProductionSecurityError) as exc_info:
            validator.validate_production_security()

        message = str(exc_info.value)
        assert "CORS_ORIGINS contains '*'" in message
        assert ("drops CORS_ALLOW_CREDENTIALS" in message) is expect_note

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

    def test_empty_admin_credentials_raises_error(self):
        """Test that an enabled admin interface without credentials is a critical issue."""
        settings = self.create_mock_settings(ADMIN_USERNAME="", ADMIN_PASSWORD="")
        validator = ProductionSecurityValidator(settings)

        with pytest.raises(ProductionSecurityError) as exc_info:
            validator.validate_production_security()

        assert "ADMIN_USERNAME" in str(exc_info.value)
        assert "ADMIN_PASSWORD" in str(exc_info.value)

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


class TestAProjectWithoutTheseFeatures:
    """The validator runs whatever features a project selected, and no more.

    ``CoreSettings`` carries none of the feature mixins, so every check that reads
    one has to answer "nothing to warn about" instead of raising.
    """

    def test_it_validates_settings_that_carry_no_feature(self):
        validator = ProductionSecurityValidator(cast(Settings, CoreSettings(ENVIRONMENT=EnvironmentOption.PRODUCTION)))

        assert validator._check_session_security() == []
        assert validator._check_admin_credentials() == []
        assert validator._get_redis_configurations() == []

    def test_the_core_checks_still_run(self):
        """Dropping features must not drop the checks that hold for every project."""
        validator = ProductionSecurityValidator(cast(Settings, CoreSettings(ENVIRONMENT=EnvironmentOption.PRODUCTION)))

        errors = validator._validate_critical_security()

        assert any("SECRET_KEY" in error for error in errors)


class TestTheSecretKeyRule:
    """What the validator refuses, and what it must never refuse."""

    def _validator(self, secret: str) -> ProductionSecurityValidator:
        return ProductionSecurityValidator(Settings(SECRET_KEY=secret, ENVIRONMENT=EnvironmentOption.PRODUCTION))

    @pytest.mark.parametrize(
        "shape",
        [
            lambda source: source.randbytes(16).hex(),
            lambda source: source.randbytes(32).hex(),
            lambda source: base64.urlsafe_b64encode(source.randbytes(24)).rstrip(b"=").decode(),
            lambda source: base64.urlsafe_b64encode(source.randbytes(32)).rstrip(b"=").decode(),
        ],
    )
    def test_every_generated_key_is_accepted(self, shape):
        """100,000 keys of each shape a generator produces, drawn from a fixed seed.

        The rules do refuse a few generated keys: one hex key in 12.6 million runs
        through eight consecutive digits, and a ``token_urlsafe`` key walks
        neighbouring keys over 0.6 of its length at around one in ten million (one
        such key in a 10,000,000 sample, none in a second). ``bp env gen-secret``
        draws again rather than printing those, and the seed here is fixed so that
        this sweep states what the rules do instead of drawing a lottery.
        """
        source = random.Random(20261004)
        refused = [key for _ in range(100_000) if is_weak_secret_key(key := shape(source))]

        assert refused == []

    @pytest.mark.parametrize(
        "secret",
        [
            "e48102bfe6ac2eac3aa8623456789a6030e4fa7dee3cd173bfb7941f2f819678",
            "YERgHz9JxnVgFvhYCDrFVjatUKju6-pj",
        ],
    )
    def test_a_key_a_generator_produced_is_refused_when_it_reads_as_a_pattern(self, secret: str):
        """Both came out of `secrets`: the first runs 2345678, the second walks the keyboard."""
        assert is_weak_secret_key(secret)

    def test_a_generated_key_reaches_the_validator_as_it_reaches_the_rules(self):
        """The validator asks the same question these sweeps ask."""
        key = secrets.token_hex(16)

        assert not self._validator(key)._is_insecure_secret_key()
        assert self._validator("insecure-secret-key-change-this")._is_insecure_secret_key()

    def test_a_passphrase_of_unrelated_words_is_accepted(self):
        assert not self._validator("brook-mellow-tundra-quartz-ripple-42")._is_insecure_secret_key()

    @pytest.mark.parametrize(
        "secret",
        [
            "",
            "short",
            "insecure-secret-key-change-this",
            "change-me-please-change-me-please-change",
            "my-super-secret-production-key-value",
            "my-company-api-signing-key-for-prod",
            "developmentdevelopmentdevelopment1",
            "12345678" * 4,
            "0123456789abcdef" * 2,
            "abcdefgh" * 4,
            "0123456789abcdefghijklmnopqrstuv",
            "a" * 64,
            "abababababababababababababababababababab",
        ],
    )
    def test_a_weak_key_is_refused(self, secret: str):
        assert self._validator(secret)._is_insecure_secret_key()

    @pytest.mark.parametrize(
        "secret",
        [
            "qwertyuiopasdfghjklzxcvbnm123456",
            "1qaz2wsx3edc4rfv5tgb6yhn7ujm8ik,",
            "monkey" * 5 + "12",
            "welcome1" * 4 + "2",
            "hunter2hunter2hunter2hunter2hunter22",
            "prodprodprodprodprodprodprodprod1",
            "Summer2026!Summer2026!Summer2026!!",
            "abc123" * 5 + "ab",
            "MyCompanyApiSigningKeyForProd2026",
            "thisismysupersecurekeyforthisapp",
        ],
    )
    def test_a_key_that_reads_as_typed_is_refused(self, secret: str):
        """Long enough and varied enough to pass an entropy floor, and still hand-written."""
        assert self._validator(secret)._is_insecure_secret_key()

    def test_a_generated_key_that_happens_to_spell_a_weak_word_is_accepted(self):
        """The rules measure a share of the whole value, not any occurrence."""
        assert not self._validator("Kq7-test-2mZr9XbW4nHt6LyPv8CdFgJs1AuEoQiRzN")._is_insecure_secret_key()
