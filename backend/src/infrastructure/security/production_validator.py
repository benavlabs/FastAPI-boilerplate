"""Production security validation.

This module provides comprehensive security validation for production environments,
checking for common misconfigurations that could lead to security vulnerabilities.
"""

import re
from urllib.parse import unquote, urlsplit

from ..config.settings import EnvironmentOption, Settings
from ..logging import get_logger

logger = get_logger()


class ProductionSecurityError(Exception):
    """Exception raised when critical security issues are found in production.

    This exception is thrown when security vulnerabilities are detected that
    could compromise the application's security posture. It indicates issues
    that should prevent the application from starting in production.

    Args:
        message: Detailed error message describing the security issues.

    Note:
        This exception is only raised for critical security issues that
        pose immediate threats to the application's security. Non-critical
        issues are logged as warnings instead.

    Example:
        ```python
        try:
            validate_production_security(settings)
        except ProductionSecurityError as e:
            logger.critical(f"Critical security issues prevent startup: {e}")
            sys.exit(1)
        ```
    """

    pass


class ProductionSecurityValidator:
    """Comprehensive security validator for production environments.

    This validator performs extensive security checks on production configurations,
    identifying potential vulnerabilities and misconfigurations that could expose
    the application to security threats.

    The validator categorizes issues into:
    - Critical errors: Issues that prevent application startup
    - Warnings: Issues that are logged but don't prevent startup

    Features:
    - Secret key strength validation
    - Database credential security checks
    - Redis configuration security analysis
    - CORS policy validation
    - Session security configuration checks
    - Admin interface security validation
    - Debug mode and documentation exposure checks

    Example:
        ```python
        validator = ProductionSecurityValidator(settings)

        try:
            validator.validate_production_security()
            logger.info("Production security validation passed")
        except ProductionSecurityError as e:
            logger.critical(f"Security validation failed: {e}")
            raise
        ```
    """

    def __init__(self, settings: Settings):
        """Initialize the production security validator.

        Args:
            settings: Application settings to validate for security issues.

        Note:
            The validator examines all security-relevant settings including
            database credentials, Redis configurations, session settings,
            and admin interface configurations.
        """
        self.settings = settings
        self.logger = get_logger()

    def validate_production_security(self) -> None:
        """Validate production security configuration comprehensively.

        Performs a complete security audit of the production configuration,
        checking for critical security issues that could compromise the
        application's security posture.

        Raises:
            ProductionSecurityError: If critical security issues are found
                                   that should prevent production deployment.

        Note:
            This method only runs validation in production environments.
            For non-production environments, it logs a debug message and returns.

            The validation process includes:
            - Critical security checks (raise exceptions)
            - Warning security checks (log warnings)
            - Comprehensive reporting of all issues found

        Example:
            ```python
            # In application startup
            try:
                validator.validate_production_security()
                logger.info("Production security validation passed")
            except ProductionSecurityError as e:
                logger.error(f"Production security validation failed: {e}")
                sys.exit(1)
            ```
        """
        if not self._is_production():
            self.logger.debug("Not in production environment, skipping security validation")
            return

        self.logger.info("Running production security validation...")

        critical_errors = self._validate_critical_security()
        if critical_errors:
            error_msg = "Critical security issues detected in production:\n" + "\n".join(
                f"  • {error}" for error in critical_errors
            )
            self.logger.error(error_msg)
            raise ProductionSecurityError(error_msg)

        self._validate_warning_security()

        self.logger.info("Production security validation completed successfully")

    def _is_production(self) -> bool:
        """Check if the application is running in production environment.

        Returns:
            True if the environment is set to production, False otherwise.

        Note:
            This method checks the ENVIRONMENT setting to determine if
            comprehensive security validation should be performed.
        """
        return self.settings.ENVIRONMENT == EnvironmentOption.PRODUCTION

    def _validate_critical_security(self) -> list[str]:
        """Validate critical security issues that should prevent startup.

        Performs checks for security vulnerabilities that pose immediate
        threats to the application's security and should prevent the
        application from starting in production.

        Returns:
            List of critical security error messages. Empty list if no
            critical issues are found.

        Note:
            Critical security issues include:
            - Insecure secret keys
            - Unprotected admin interfaces
            - Default database credentials
            - Empty database passwords

            These issues can lead to immediate security breaches and
            should be fixed before production deployment.

        Example:
            Critical issues that would be detected:
            - SECRET_KEY using default values
            - Admin interface with no IP restrictions
            - Database using 'postgres' password
            - Empty database password
        """
        errors = []

        if self._is_insecure_secret_key():
            errors.append(
                "SECRET_KEY is using default or insecure value. "
                "This compromises session security, CSRF protection, and JWT tokens. "
                "Generate a strong, unique secret key for production."
            )

        if self._is_database_using_default_credentials():
            errors.append(
                "Database is using default credentials (password 'postgres'). "
                "This is a well-known default that attackers will try first. "
                "Use a strong, unique password for production."
            )

        if self._is_database_password_empty():
            errors.append(
                "Database password is empty (POSTGRES_PASSWORD is not set). "
                "This leaves your database completely unprotected. "
                "Set a strong password for production."
            )

        return errors

    def _validate_warning_security(self) -> None:
        """Log warnings for security concerns that don't prevent startup.

        Identifies security issues that should be addressed but don't pose
        immediate threats severe enough to prevent application startup.
        These issues are logged as warnings for review and remediation.

        Note:
            Warning-level security issues include:
            - Redis instances without passwords
            - Overly permissive CORS settings
            - Debug mode enabled in production
            - API documentation exposed
            - Insecure session configurations
            - Weak admin credentials

            While these don't prevent startup, they should be addressed
            to maintain optimal security posture.

        Example:
            Warning issues that would be detected:
            - CORS_ORIGINS set to '*'
            - Redis without password authentication
            - Session timeout too long
            - Weak admin usernames or passwords
        """
        warnings = []

        redis_warnings = self._check_redis_security()
        warnings.extend(redis_warnings)

        if self._is_database_url_without_password():
            warnings.append(
                "DATABASE_URL is set but contains no password. This is expected with "
                "IAM or certificate-based authentication, but is a mistake otherwise — "
                "confirm the database is not reachable without credentials."
            )

        if self._is_cors_too_permissive():
            warnings.append(
                "CORS_ORIGINS is set to '*' (allow all origins). This can enable "
                "cross-origin attacks. Consider restricting to specific domains in production."
            )

        if self._is_debug_enabled():
            warnings.append(
                "DEBUG mode is enabled in production. This can expose sensitive information "
                "in error responses and enable debug endpoints. Set DEBUG=false for production."
            )

        docs_warning = self._check_docs_security()
        if docs_warning:
            warnings.append(docs_warning)

        session_warnings = self._check_session_security()
        warnings.extend(session_warnings)

        admin_warnings = self._check_admin_credentials()
        warnings.extend(admin_warnings)

        for warning in warnings:
            self.logger.warning(f"PRODUCTION SECURITY WARNING: {warning}")

        if warnings:
            self.logger.warning(
                f"Found {len(warnings)} production security warnings. "
                "While not critical, these should be reviewed for optimal security."
            )

    def _is_insecure_secret_key(self) -> bool:
        """Check if SECRET_KEY is insecure or uses default values.

        Analyzes the secret key for common security weaknesses including
        default values, predictable patterns, and insufficient entropy.

        Returns:
            True if the secret key is insecure, False otherwise.

        Note:
            The validation checks for:
            - Empty or missing secret keys
            - Common default values and patterns
            - Insufficient length (< 32 characters)
            - Predictable patterns and repetition
            - Common weak strings

            A secure secret key should be:
            - At least 32 characters long
            - Randomly generated
            - Unique to the application
            - Free of predictable patterns
        """
        secret = self.settings.SECRET_KEY

        if not secret:
            return True

        insecure_patterns = [
            "insecure-secret-key-change-this",
            "change-me",
            "change-this",
            "default",
            "secret",
            "password",
            "secretkey",
            "key",
            "123456",
            "abc123",
            "test",
            "dev",
            "development",
        ]

        secret_lower = secret.lower()
        if any(pattern in secret_lower for pattern in insecure_patterns):
            return True

        if len(secret) < 32:
            return True

        if self._has_predictable_pattern(secret):
            return True

        return False

    def _has_predictable_pattern(self, secret: str) -> bool:
        """Check if secret has predictable patterns that reduce security.

        Args:
            secret: The secret string to analyze for patterns.

        Returns:
            True if predictable patterns are found, False otherwise.

        Note:
            Predictable patterns include:
            - Repeated characters (e.g., "aaaa", "1111")
            - Sequential characters (e.g., "1234", "abcd")
            - Common keyboard patterns (e.g., "qwerty")

            These patterns reduce the entropy of the secret key and
            make it more susceptible to brute force attacks.
        """
        if re.search(r"(.)\1{3,}", secret):
            return True

        if "1234" in secret or "abcd" in secret.lower() or "qwerty" in secret.lower():
            return True

        return False

    def _is_admin_access_completely_open(self) -> bool:
        """Check if admin interface has no access restrictions.

        Returns:
            True if admin access is completely open, False otherwise.

        Note:
            The admin interface uses SQLAdmin with session-based authentication.
            Additional IP restrictions should be handled at the reverse proxy level
            (e.g., nginx, caddy) in production environments.
        """
        return False

    @staticmethod
    def _password_from_url(url: str) -> str | None:
        """Extract the password component of a database URL.

        Args:
            url: A database URL, with or without credentials.

        Returns:
            The decoded password, or None if the URL carries none or cannot be parsed.
        """
        try:
            password = urlsplit(url).password
        except ValueError:
            return None

        return unquote(password) if password is not None else None

    def _effective_database_password(self) -> str | None:
        """Get the password the application will actually connect with.

        A `DATABASE_URL` in the environment overrides every `POSTGRES_*` setting,
        so a deployment against a managed provider (Neon, RDS, Cloud SQL) carries
        its real credentials in that URL while `POSTGRES_PASSWORD` keeps its
        default. Reading `POSTGRES_PASSWORD` alone would flag such a deployment as
        insecure and refuse to start.

        Returns:
            The password embedded in `DATABASE_URL` when one is set, otherwise
            `POSTGRES_PASSWORD`. None means an explicit URL was given but carries
            no password at all, or could not be parsed.
        """
        if not self.settings.DATABASE_URL_OVERRIDE:
            return self.settings.POSTGRES_PASSWORD

        return self._password_from_url(self.settings.DATABASE_URL_OVERRIDE)

    def _is_database_using_default_credentials(self) -> bool:
        """Check if database is using well-known default credentials.

        Returns:
            True if database is using default credentials, False otherwise.

        Note:
            The default PostgreSQL password "postgres" is well-known and
            commonly targeted by attackers. Production systems should
            use strong, unique passwords.
        """
        return self._effective_database_password() == "postgres"

    def _is_database_password_empty(self) -> bool:
        """Check if database password is empty or missing.

        Returns:
            True if database password is empty, False otherwise.

        Note:
            Empty database passwords leave the database completely
            unprotected and accessible to anyone who can reach it.

            A `DATABASE_URL` with no password at all is not treated as an error —
            authentication may be handled outside the connection string (IAM,
            client certificates, a trusted socket). That case is warned about
            instead, since it cannot be verified from here.
        """
        password = self._effective_database_password()
        if password is None:
            return False

        return not password or password.strip() == ""

    def _is_database_url_without_password(self) -> bool:
        """Check if an explicit DATABASE_URL carries no password.

        Returns:
            True if `DATABASE_URL` is set but has no password component,
            False otherwise.
        """
        return bool(self.settings.DATABASE_URL_OVERRIDE) and self._effective_database_password() is None

    def _check_redis_security(self) -> list[str]:
        """Check Redis security configuration for all Redis instances.

        Analyzes all Redis configurations used by the application for
        security issues including authentication and encryption.

        Returns:
            List of Redis security warning messages.

        Note:
            Redis security checks include:
            - Password authentication for all instances
            - SSL/TLS encryption for remote connections
            - Instance isolation between services

            Multiple Redis instances may be configured for different
            services (cache, rate limiting, sessions, admin).
        """
        warnings = []

        redis_configs = self._get_redis_configurations()

        for config in redis_configs:
            if not config["password"]:
                warnings.append(
                    f"Redis instance for {config['service']} ({config['host']}:{config['port']} "
                    f"DB {config['db']}) has no password protection. Consider setting a password "
                    f"to prevent unauthorized access."
                )

            if not config["ssl"] and config["host"] not in ["localhost", "127.0.0.1"]:
                warnings.append(
                    f"Redis instance for {config['service']} ({config['host']}:{config['port']}) "
                    f"is not using SSL/TLS encryption. Consider enabling SSL for production."
                )

        same_instance_warning = self._check_redis_instance_sharing()
        if same_instance_warning:
            warnings.append(same_instance_warning)

        return warnings

    def _get_redis_configurations(self) -> list[dict]:
        """Get all Redis configurations used by the application.

        Returns:
            List of Redis configuration dictionaries containing connection
            details, authentication, and service information.

        Note:
            This method collects Redis configurations from all services
            that may use Redis including cache, rate limiting, admin
            interface, and session storage.
        """
        configs = []

        if self.settings.CACHE_BACKEND == "redis":
            configs.append(
                {
                    "service": "cache",
                    "host": self.settings.CACHE_REDIS_HOST,
                    "port": self.settings.CACHE_REDIS_PORT,
                    "db": self.settings.CACHE_REDIS_DB,
                    "password": self.settings.CACHE_REDIS_PASSWORD,
                    "ssl": False,
                }
            )

        if self.settings.RATE_LIMITER_BACKEND == "redis":
            configs.append(
                {
                    "service": "rate_limiter",
                    "host": self.settings.RATE_LIMITER_REDIS_HOST,
                    "port": self.settings.RATE_LIMITER_REDIS_PORT,
                    "db": self.settings.RATE_LIMITER_REDIS_DB,
                    "password": self.settings.RATE_LIMITER_REDIS_PASSWORD,
                    "ssl": False,
                }
            )

        if self.settings.SESSION_BACKEND == "redis":
            configs.append(
                {
                    "service": "sessions",
                    "host": self.settings.CACHE_REDIS_HOST,
                    "port": self.settings.CACHE_REDIS_PORT,
                    "db": self.settings.CACHE_REDIS_DB,
                    "password": self.settings.CACHE_REDIS_PASSWORD,
                    "ssl": False,
                }
            )

        return configs

    def _check_redis_instance_sharing(self) -> str:
        """Check if the same Redis instance is used by multiple services.

        Returns:
            Warning message if Redis instance sharing is detected,
            empty string otherwise.

        Note:
            While Redis instance sharing is not a security vulnerability,
            it can lead to data conflicts and performance issues. Best
            practice is to use separate Redis databases or instances
            for different services.
        """
        configs = self._get_redis_configurations()

        instances: dict[str, list[str]] = {}
        for config in configs:
            instance_key = f"{config['host']}:{config['port']}:{config['db']}"
            if instance_key not in instances:
                instances[instance_key] = []
            instances[instance_key].append(config["service"])

        shared_instances = {k: v for k, v in instances.items() if len(v) > 1}

        if shared_instances:
            shared_details = []
            for instance, services in shared_instances.items():
                shared_details.append(f"{instance} (used by: {', '.join(services)})")

            return (
                f"Multiple services are sharing the same Redis instance: {'; '.join(shared_details)}. "
                f"Consider using separate Redis databases or instances for different services "
                f"to improve isolation and prevent data conflicts."
            )

        return ""

    def _is_cors_too_permissive(self) -> bool:
        """Check if CORS is configured too permissively.

        Returns:
            True if CORS allows all origins, False otherwise.

        Note:
            CORS configured with '*' allows any origin to make requests
            to the API, which can enable cross-origin attacks. Production
            applications should restrict CORS to specific domains.
        """
        return self.settings.CORS_ENABLED and "*" in self.settings.CORS_ORIGINS_LIST

    def _is_debug_enabled(self) -> bool:
        """Check if debug mode is enabled in production.

        Returns:
            True if debug mode is enabled, False otherwise.

        Note:
            Debug mode can expose sensitive information in error responses
            and enable debug endpoints that should not be available in
            production environments.
        """
        return self.settings.DEBUG

    def _check_docs_security(self) -> str:
        """Check API documentation security configuration.

        Returns:
            Warning message if documentation is exposed, empty string otherwise.

        Note:
            API documentation exposes the complete API schema and endpoints,
            which can provide valuable information to attackers. Consider
            restricting access or disabling documentation in production.
        """
        if self.settings.ENABLE_DOCS_IN_PRODUCTION:
            return (
                "API documentation is enabled in production (ENABLE_DOCS_IN_PRODUCTION=true). "
                "This exposes your API schema and endpoints publicly. Ensure proper access "
                "controls are in place or disable docs in production."
            )
        return ""

    def _check_session_security(self) -> list[str]:
        """Check session security configuration.

        Returns:
            List of session security warning messages.

        Note:
            Session security checks include:
            - Secure cookie configuration
            - Appropriate session timeout settings
            - CSRF protection enablement

            Insecure session configurations can lead to session hijacking
            and other session-based attacks.
        """
        warnings: list[str] = []

        if not self.settings.SESSION_SECURE_COOKIES:
            warnings.append(
                "SESSION_SECURE_COOKIES is disabled. This allows session cookies to be "
                "transmitted over unencrypted HTTP connections, making them vulnerable "
                "to interception. Enable secure cookies in production."
            )

        if self.settings.SESSION_TIMEOUT_MINUTES > 120:
            warnings.append(
                f"Session timeout is set to {self.settings.SESSION_TIMEOUT_MINUTES} minutes "
                f"(more than 2 hours). Long session timeouts increase security risk if "
                f"a session is compromised. Consider reducing the timeout for production."
            )

        if not self.settings.CSRF_ENABLED:
            warnings.append(
                "CSRF protection is disabled. This makes your application vulnerable to "
                "Cross-Site Request Forgery attacks. Enable CSRF protection in production."
            )

        return warnings

    def _check_admin_credentials(self) -> list[str]:
        """Check admin credentials security.

        Returns:
            List of admin credential security warning messages.

        Note:
            Admin credential security checks include:
            - Username predictability
            - Password strength and length
            - Common weak password detection

            Weak admin credentials are a common attack vector and should
            be strengthened in production environments.
        """
        warnings: list[str] = []

        if not self.settings.ADMIN_ENABLED:
            return warnings

        if not self.settings.ADMIN_USERNAME or not self.settings.ADMIN_PASSWORD:
            return warnings

        weak_usernames = ["admin", "administrator", "root", "user", "test", "demo"]
        if self.settings.ADMIN_USERNAME.lower() in weak_usernames:
            warnings.append(
                f"Admin username '{self.settings.ADMIN_USERNAME}' is predictable. "
                f"Consider using a less obvious username for better security."
            )

        password = self.settings.ADMIN_PASSWORD
        if len(password) < 12:
            warnings.append(
                "Admin password is shorter than 12 characters. Use a longer, "
                "stronger password for admin accounts in production."
            )

        weak_passwords = {
            "password",
            "123456",
            "admin",
            "password123",
            "admin123",
            "qwerty",
            "letmein",
            "welcome",
            "changeme",
            "123456",
            "12345678",
            "1234",
            "123",
            "12345",
            "123456789",
            "adminisp",
            "demo",
            "root",
            "123123",
            "admin@123",
            "123456aA@",
            "01031974",
            "Admin@123",
            "111111",
            "admin1234",
            "admin1",
        }
        if password.lower() in weak_passwords:
            warnings.append(
                "Admin password appears to be a common weak password. Use a strong, unique password for admin accounts."
            )

        return warnings


def validate_production_security(settings: Settings) -> None:
    """Convenience function to validate production security configuration.

    Creates a ProductionSecurityValidator instance and runs comprehensive
    security validation on the provided settings.

    Args:
        settings: Application settings to validate for security issues.

    Raises:
        ProductionSecurityError: If critical security issues are found.

    Note:
        This is a convenience function that provides a simple interface
        for production security validation. It's equivalent to creating
        a validator instance and calling validate_production_security().

    Example:
        ```python
        from infrastructure.security import validate_production_security
        from infrastructure.config import get_settings

        settings = get_settings()

        try:
            validate_production_security(settings)
            logger.info("Production security validation passed")
        except ProductionSecurityError as e:
            logger.critical(f"Security validation failed: {e}")
            sys.exit(1)
        ```
    """
    validator = ProductionSecurityValidator(settings)
    validator.validate_production_security()
