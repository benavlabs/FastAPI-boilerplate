"""Infrastructure configuration enums."""

from enum import StrEnum


class CacheBackend(StrEnum):
    """Cache backend types.

    Supported backends for caching and rate limiting.
    """

    REDIS = "redis"
    MEMCACHED = "memcached"
    MEMORY = "memory"


class SessionBackend(StrEnum):
    """Session storage backend types.

    Supported backends for session storage (crudauth supports redis and memory only).
    """

    REDIS = "redis"
    MEMORY = "memory"


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
