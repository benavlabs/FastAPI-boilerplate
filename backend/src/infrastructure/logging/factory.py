"""Smart logger factory with automatic configuration and settings integration.

This module provides the main interface for obtaining loggers throughout
the application. It automatically detects calling modules, applies
configuration based on settings, and provides a simple API for getting
properly configured loggers.

The factory integrates with the application's settings system to provide
environment-aware logging configuration while maintaining a simple API
for developers.
"""

import inspect
import logging
from collections.abc import MutableMapping
from threading import Lock
from typing import Any, Union

from ..config.settings import get_settings
from .config import get_configured_logger, setup_logging_configuration

_logging_configured = False
_configuration_lock = Lock()


def get_logger(name: str | None = None, **extra_context) -> logging.Logger | logging.LoggerAdapter:
    """Get a properly configured logger with automatic module detection.

    This is the main interface for obtaining loggers throughout the application.
    It automatically detects the calling module name if not provided and ensures
    the logging system is properly configured based on application settings.

    Args:
        name: Logger name. If None, automatically detects from calling module.
        **extra_context: Additional context to include in log records.

    Returns:
        Configured logger instance ready for use.

    Example:
        ```python
        # Auto-detect module name
        logger = get_logger()
        logger.info("Application started")

        # Explicit name
        logger = get_logger("my.custom.logger")
        logger.debug("Custom logger message")

        # With extra context
        logger = get_logger(service="auth", version="1.0")
        logger.info("Service initialized", extra={"user_count": 150})
        ```
    """
    _ensure_logging_configured()

    if name is None:
        name = _detect_calling_module()

    base_logger = get_configured_logger(name)

    if extra_context:
        logger: logging.Logger | logging.LoggerAdapter = logging.LoggerAdapter(base_logger, extra_context)
    else:
        logger = base_logger

    return logger


def configure_logging() -> None:
    """Manually trigger logging configuration.

    This function can be called to explicitly configure logging,
    though it's typically called automatically when first logger
    is requested. Useful for early application setup.
    """
    global _logging_configured

    with _configuration_lock:
        if not _logging_configured:
            setup_logging_configuration()
            _logging_configured = True

            logger = logging.getLogger(__name__)
            try:
                settings = get_settings()
                logger.info(
                    f"Logging configured for {settings.ENVIRONMENT.value} environment",
                    extra={
                        "log_level": settings.LOG_LEVEL,
                        "log_format": settings.LOG_FORMAT,
                        "console_enabled": settings.LOG_CONSOLE_ENABLED,
                        "file_enabled": settings.LOG_FILE_ENABLED,
                    },
                )
            except Exception:
                logger.info("Logging configured for development environment")


def _ensure_logging_configured() -> None:
    """Ensure logging is configured, calling setup if needed."""
    global _logging_configured

    if not _logging_configured:
        configure_logging()


def _detect_calling_module() -> str:
    """Detect the module name of the calling function.

    Uses the call stack to determine the module name of the code
    that called get_logger(). This provides automatic module
    detection for convenience.

    Returns:
        Module name of the calling code.
    """
    frame = inspect.currentframe()

    try:
        for _ in range(2):
            if frame is None:
                break
            frame = frame.f_back

        if frame is not None:
            module_name = frame.f_globals.get("__name__", "unknown")
            return str(module_name)
        else:
            return "unknown"

    finally:
        del frame


class LoggerAdapter(logging.LoggerAdapter):
    """Enhanced logger adapter that merges context automatically.

    Extends the standard LoggerAdapter to provide better context
    merging and handling of extra parameters. This ensures that
    context provided when creating the logger is automatically
    included in all log records.
    """

    def __init__(self, logger: logging.Logger, extra: dict[str, Any]):
        """Initialize the adapter with a logger and extra context.

        Args:
            logger: The underlying logger instance.
            extra: Dictionary of extra context to include in all records.
        """
        super().__init__(logger, extra)

    def process(self, msg: str, kwargs: MutableMapping[str, Any]) -> tuple[str, MutableMapping[str, Any]]:
        """Process the log record to merge context.

        Merges the adapter's extra context with any context
        provided in the specific log call.

        Args:
            msg: The log message.
            kwargs: Keyword arguments from the log call.

        Returns:
            Tuple of (message, merged_kwargs).
        """
        extra = kwargs.get("extra", {})

        adapter_extra = self.extra if isinstance(self.extra, dict) else {}
        if isinstance(extra, dict):
            merged_extra = {**adapter_extra, **extra}
        else:
            merged_extra = adapter_extra

        kwargs["extra"] = merged_extra

        return msg, kwargs


def create_child_logger(
    parent_logger: logging.Logger, child_name: str, **extra_context
) -> Union[logging.Logger, "LoggerAdapter"]:
    """Create a child logger with additional context.

    Creates a child logger that inherits from the parent while
    adding additional context. Useful for creating specialized
    loggers for specific components or operations.

    Args:
        parent_logger: The parent logger to inherit from.
        child_name: Name suffix for the child logger.
        **extra_context: Additional context for the child logger.

    Returns:
        Child logger with combined context.

    Example:
        ```python
        service_logger = get_logger()
        auth_logger = create_child_logger(service_logger, "auth", component="authentication")
        auth_logger.info("User logged in")  # Will include component=authentication
        ```
    """
    child_logger_name = f"{parent_logger.name}.{child_name}"
    base_child_logger = get_configured_logger(child_logger_name)

    if extra_context:
        child_logger: logging.Logger | LoggerAdapter = LoggerAdapter(base_child_logger, extra_context)
    else:
        child_logger = base_child_logger

    return child_logger


def get_logger_with_correlation_id(correlation_id: str, name: str | None = None) -> LoggerAdapter:
    """Get a logger with automatic correlation ID inclusion.

    Creates a logger that automatically includes the provided
    correlation ID in all log records. Useful for request
    tracing and distributed system debugging.

    Args:
        correlation_id: The correlation ID to include.
        name: Logger name, auto-detected if None.

    Returns:
        Logger with correlation ID context.

    Example:
        ```python
        logger = get_logger_with_correlation_id("req-123456")
        logger.info("Processing request")  # Will include correlation_id=req-123456
        ```
    """
    logger = get_logger(name or _detect_calling_module())
    if isinstance(logger, logging.LoggerAdapter):
        base_logger = logger.logger
    else:
        base_logger = logger
    return LoggerAdapter(base_logger, {"correlation_id": correlation_id})
