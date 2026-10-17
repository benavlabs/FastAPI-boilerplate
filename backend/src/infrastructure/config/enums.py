"""Infrastructure configuration enums."""

from enum import StrEnum


class CacheBackend(StrEnum):
    """Cache backend types."""

    REDIS = "redis"
    MEMCACHED = "memcached"
    MEMORY = "memory"


class EmailBackend(StrEnum):
    """How account emails are delivered."""

    CONSOLE = "console"
    SMTP = "smtp"


class SessionBackend(StrEnum):
    """Session storage backend types.

    ``DATABASE`` keeps sessions in two tables of the project's own database, which
    several workers share without a Redis.
    """

    REDIS = "redis"
    MEMORY = "memory"
    DATABASE = "database"


class RateLimiterBackend(StrEnum):
    """Rate limiter backend types.

    ``MEMORY`` counts in the process, so each worker counts a login lockout on its own.
    ``REDIS`` and ``DATABASE`` are shared by every worker.
    """

    REDIS = "redis"
    MEMORY = "memory"
    DATABASE = "database"


class TaskiqBrokerType(StrEnum):
    """Taskiq message broker types.

    Supported message brokers for async task processing.
    """

    REDIS = "redis"
    RABBITMQ = "rabbitmq"


class LogLevel(StrEnum):
    """Log level types.

    Standard Python logging levels.
    """

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class LogFormat(StrEnum):
    """Log format types.

    Supported log output formats.
    """

    SIMPLE = "simple"
    DETAILED = "detailed"
    STRUCTURED = "structured"
    JSON = "json"
