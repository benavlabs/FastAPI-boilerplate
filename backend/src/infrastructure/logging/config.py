"""Logging configuration module for environment-aware setup.

This module provides the main configuration logic that sets up logging
based on application settings and environment. It intelligently configures
different handlers, formatters, and levels based on the deployment context.

Configuration Logic:
- Development: Verbose console logging with colors
- Staging: Structured logging with file output
- Production: Optimized logging with JSON format
- Testing: Minimal logging to avoid test output noise
"""

import contextvars
import inspect
import logging
import logging.config
import threading
import uuid

from ..config.enums import LogFormat
from ..config.settings import EnvironmentOption, get_settings
from .handlers import (
    create_console_handler,
    create_file_handler,
    create_null_handler,
)


def setup_logging_configuration() -> None:
    """Set up logging configuration based on application settings.

    This function configures the root logger and sets up appropriate
    handlers based on the current environment and settings. It should
    be called once during application startup.

    Configuration by Environment:
    - Development: Console with colors, detailed format, DEBUG level
    - Staging: Console + file, structured format, INFO level
    - Production: Console + file, JSON format, WARNING level
    - Testing: Minimal output to avoid noise
    """
    settings = get_settings()

    logging.getLogger().handlers.clear()

    if settings.ENVIRONMENT == EnvironmentOption.DEVELOPMENT:
        _configure_development_logging(settings)
    elif settings.ENVIRONMENT == EnvironmentOption.STAGING:
        _configure_staging_logging(settings)
    elif settings.ENVIRONMENT == EnvironmentOption.PRODUCTION:
        _configure_production_logging(settings)
    else:
        _configure_development_logging(settings)

    root_logger = logging.getLogger()
    root_logger.setLevel(settings.LOG_LEVEL_INT)

    if settings.ENVIRONMENT == EnvironmentOption.PRODUCTION:
        _configure_noisy_loggers()


def _format_for(settings, default: LogFormat) -> str:
    """The configured log format, or the one this environment uses by default."""
    return settings.LOG_FORMAT or default.value


def _configure_development_logging(settings) -> None:
    """Configure logging for development environment.

    Features:
    - Colored console output for better readability
    - Detailed formatting with timestamps
    - DEBUG level for comprehensive information
    - Optional file logging if enabled
    """
    handlers = []

    if settings.LOG_CONSOLE_ENABLED:
        console_level = logging.DEBUG if settings.LOG_DEVELOPMENT_VERBOSE else settings.LOG_LEVEL_INT
        console_handler = create_console_handler(
            format_type=_format_for(settings, LogFormat.DETAILED),
            level=console_level,
            use_colors=True,
        )
        handlers.append(console_handler)

    if settings.LOG_FILE_ENABLED:
        file_handler = create_file_handler(
            filepath=settings.LOG_FILE_PATH,
            format_type=_format_for(settings, LogFormat.STRUCTURED),
            level=logging.DEBUG,
            max_bytes=settings.LOG_FILE_MAX_SIZE,
            backup_count=settings.LOG_FILE_BACKUP_COUNT,
        )
        handlers.append(file_handler)

    root_logger = logging.getLogger()
    for handler in handlers:
        root_logger.addHandler(handler)


def _configure_staging_logging(settings) -> None:
    """Configure logging for staging environment.

    Features:
    - Structured console output for machine parsing
    - File logging enabled by default
    - INFO level for balanced detail
    """
    handlers = []

    if settings.LOG_CONSOLE_ENABLED:
        console_handler = create_console_handler(
            format_type=_format_for(settings, LogFormat.STRUCTURED),
            level=settings.LOG_LEVEL_INT,
            use_colors=False,
        )
        handlers.append(console_handler)

    file_enabled = settings.LOG_FILE_ENABLED
    if file_enabled:
        file_handler = create_file_handler(
            filepath=settings.LOG_FILE_PATH,
            format_type=_format_for(settings, LogFormat.STRUCTURED),
            level=logging.DEBUG,
            max_bytes=settings.LOG_FILE_MAX_SIZE,
            backup_count=settings.LOG_FILE_BACKUP_COUNT,
        )
        handlers.append(file_handler)

    root_logger = logging.getLogger()
    for handler in handlers:
        root_logger.addHandler(handler)


def _configure_production_logging(settings) -> None:
    """Configure logging for production environment.

    Features:
    - JSON console output for log aggregation
    - File logging with rotation
    - Optimized log levels to reduce noise
    - Performance optimizations
    """
    handlers = []

    if settings.LOG_CONSOLE_ENABLED:
        console_level = logging.WARNING if settings.LOG_PRODUCTION_OPTIMIZE else settings.LOG_LEVEL_INT
        console_handler = create_console_handler(
            format_type=_format_for(settings, LogFormat.JSON),
            level=console_level,
            use_colors=False,
        )
        handlers.append(console_handler)

    if settings.LOG_FILE_ENABLED:
        file_handler = create_file_handler(
            filepath=settings.LOG_FILE_PATH,
            format_type=_format_for(settings, LogFormat.JSON),
            level=settings.LOG_LEVEL_INT,
            max_bytes=settings.LOG_FILE_MAX_SIZE,
            backup_count=settings.LOG_FILE_BACKUP_COUNT,
        )
        handlers.append(file_handler)

    root_logger = logging.getLogger()
    for handler in handlers:
        root_logger.addHandler(handler)


def _configure_noisy_loggers() -> None:
    """Configure noisy third-party loggers to reduce noise in production.

    Sets appropriate log levels for common third-party libraries that
    tend to be verbose, ensuring they don't overwhelm production logs.
    """
    noisy_loggers = {
        "urllib3.connectionpool": logging.WARNING,
        "requests.packages.urllib3": logging.WARNING,
        "asyncpg": logging.WARNING,
        "sqlalchemy.engine": logging.WARNING,
        "sqlalchemy.dialects": logging.WARNING,
        "sqlalchemy.pool": logging.WARNING,
        "aiomcache": logging.WARNING,
        "redis": logging.WARNING,
    }

    for logger_name, level in noisy_loggers.items():
        logger = logging.getLogger(logger_name)
        logger.setLevel(level)


def configure_testing_logging() -> None:
    """Configure minimal logging for testing environments.

    Sets up logging that minimizes output during tests while still
    capturing important error information. Can be called from test
    fixtures to override normal logging configuration.
    """
    root_logger = logging.getLogger()
    root_logger.handlers.clear()

    root_logger.addHandler(create_null_handler())

    root_logger.setLevel(logging.ERROR)

    test_loggers = {
        "sqlalchemy.engine": logging.ERROR,
        "asyncpg": logging.ERROR,
    }

    for logger_name, level in test_loggers.items():
        logger = logging.getLogger(logger_name)
        logger.setLevel(level)


def get_configured_logger(name: str) -> logging.Logger:
    """Get a logger that inherits from the configured root logger.

    This function returns a logger that will use the handlers and
    configuration set up by setup_logging_configuration().

    Args:
        name: The name for the logger, typically __name__

    Returns:
        Configured logger instance
    """
    return logging.getLogger(name)


def add_correlation_id_filter() -> None:
    """Add a filter to automatically include correlation IDs in log records.

    This can be used to add request correlation IDs or trace IDs to
    all log records automatically. Adds the filter to the root logger
    so all child loggers inherit the correlation ID functionality.
    """
    root_logger = logging.getLogger()
    correlation_filter = CorrelationIdFilter()
    root_logger.addFilter(correlation_filter)


class CorrelationIdFilter(logging.Filter):
    """Logging filter that adds correlation ID to log records.

    This filter checks for correlation ID in context variables and adds
    it to log records for distributed tracing and request tracking.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        """Add correlation ID to log record if available.

        Args:
            record: Log record to modify

        Returns:
            True to allow the record to be processed
        """
        try:
            correlation_id = self._get_correlation_id()
        except Exception:
            correlation_id = None

        setattr(record, "correlation_id", correlation_id or "no-correlation")

        if not hasattr(record, "extra"):
            setattr(record, "extra", {})
        getattr(record, "extra")["correlation_id"] = getattr(record, "correlation_id")

        return True

    def _get_correlation_id(self) -> str | None:
        """Get correlation ID from various sources.

        Checks multiple sources for correlation ID:
        1. Context variables (from middleware)
        2. Thread local storage
        3. Request headers (if available)

        Returns:
            Correlation ID string or None if not found
        """
        try:
            correlation_id = correlation_id_var.get()
            if correlation_id:
                return correlation_id
        except (LookupError, AttributeError):
            pass

        try:
            thread_local = getattr(threading.current_thread(), "correlation_id", None)
            if thread_local:
                return str(thread_local)
        except AttributeError:
            pass

        try:
            frame = inspect.currentframe()
            while frame:
                if "request" in frame.f_locals:
                    request = frame.f_locals["request"]
                    if hasattr(request, "state") and hasattr(request.state, "correlation_id"):
                        return str(request.state.correlation_id)
                    if hasattr(request, "headers"):
                        correlation_id = request.headers.get("x-correlation-id") or request.headers.get("x-request-id")
                        if correlation_id:
                            return str(correlation_id)
                frame = frame.f_back
        except Exception:
            pass

        return None


correlation_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("correlation_id")


def set_correlation_id(correlation_id: str) -> None:
    """Set correlation ID in context for current request.

    Args:
        correlation_id: Unique identifier for request tracing
    """
    correlation_id_var.set(correlation_id)


def get_correlation_id() -> str | None:
    """Get current correlation ID from context.

    Returns:
        Current correlation ID or None if not set
    """
    try:
        return correlation_id_var.get()
    except LookupError:
        return None


def generate_correlation_id() -> str:
    """Generate a new correlation ID.

    Returns:
        New UUID-based correlation ID
    """
    return str(uuid.uuid4())


def reconfigure_logger_level(logger_name: str, level: int) -> None:
    """Dynamically reconfigure a specific logger's level.

    Useful for debugging specific components without changing
    the entire logging configuration.

    Args:
        logger_name: Name of the logger to reconfigure
        level: New logging level (logging.DEBUG, INFO, etc.)
    """
    logger = logging.getLogger(logger_name)
    logger.setLevel(level)

    logging.getLogger(__name__).info(f"Logger level changed: {logger_name} -> {logging.getLevelName(level)}")
