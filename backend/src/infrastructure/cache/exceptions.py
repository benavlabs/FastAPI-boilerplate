class CacheException(Exception):
    """Base exception for all cache-related errors in the system.

    Serves as the parent class for all cache-specific exceptions,
    providing a common interface for error handling throughout
    the caching infrastructure.

    Args:
        message: Detailed error message describing the cache failure.

    Note:
        This base class should not be raised directly. Instead, use
        specific subclasses that better describe the type of cache error.

        All cache-related exceptions inherit from this base class,
        allowing for comprehensive error handling with a single
        exception type when needed.

    Example:
        ```python
        try:
            # Cache operations
            await cache.set("key", "value")
        except CacheException as e:
            logger.error(f"Cache operation failed: {e}")
            # Handle any cache-related error
        ```
    """

    pass


class CacheBackendNotAvailableError(CacheException):
    """Raised when the cache backend is not available or unreachable.

    This exception is thrown when the cache backend (Redis, Memcached, etc.)
    cannot be reached, is not responding, or has failed health checks.

    Args:
        message: Detailed error message about the backend availability issue.

    Note:
        This exception typically indicates:
        - Network connectivity issues
        - Backend service is down or restarting
        - Authentication or authorization failures
        - Configuration errors preventing connection
        - Resource exhaustion on the backend

    Example:
        ```python
        try:
            await cache.ping()
        except CacheBackendNotAvailableError:
            logger.warning("Cache backend unavailable, falling back to database")
            # Implement fallback logic
        ```
    """

    def __init__(self, message: str = "Cache backend is not available."):
        self.message = message
        super().__init__(self.message)


class BackendNotFoundError(CacheException):
    """Raised when the specified cache backend is not found or registered.

    This exception occurs when trying to use a cache backend that hasn't
    been registered with the cache provider or doesn't exist in the
    backend registry.

    Args:
        message: Detailed error message about the missing backend.

    Note:
        This exception typically indicates:
        - Backend name typo in configuration
        - Backend not properly registered during initialization
        - Missing backend dependencies or imports
        - Configuration mismatch between environments

    Example:
        ```python
        try:
            cache = get_cache_backend("nonexistent_backend")
        except BackendNotFoundError as e:
            logger.error(f"Cache backend not found: {e}")
            # Fall back to default backend or raise configuration error
        ```
    """

    def __init__(self, message: str = "Cache backend not found."):
        self.message = message
        super().__init__(self.message)


class InvalidRequestError(CacheException):
    """Raised when an invalid request configuration is detected.

    This exception occurs when cache operations receive invalid
    configuration parameters, malformed requests, or incompatible
    operation settings.

    Args:
        message: Detailed error message about the invalid request configuration.

    Note:
        This exception typically indicates:
        - Invalid cache key format or characters
        - Negative or zero expiration times
        - Incompatible serialization settings
        - Invalid pattern syntax for pattern-based operations
        - Malformed cache decorator parameters

    Example:
        ```python
        try:
            # Invalid expiration time
            await cache.set("key", "value", expiration=-1)
        except InvalidRequestError as e:
            logger.error(f"Invalid cache request: {e}")
            # Use default expiration or fix the configuration
        ```
    """

    def __init__(self, message: str = "Invalid request configuration for cache."):
        self.message = message
        super().__init__(self.message)


class MissingClientError(CacheException):
    """Raised when the cache client is missing or not initialized.

    This exception occurs when attempting to use cache operations
    before the cache client has been properly initialized or when
    the client becomes unavailable during runtime.

    Args:
        message: Detailed error message about the missing client.

    Note:
        This exception typically indicates:
        - Cache client not initialized during startup
        - Client connection lost during operation
        - Configuration issues preventing client creation
        - Dependency injection failures
        - Client cleanup during shutdown

    Example:
        ```python
        try:
            await cache.get("key")
        except MissingClientError:
            logger.error("Cache client not initialized")
            # Initialize client or use fallback
            await initialize_cache_client()
        ```
    """

    def __init__(self, message: str = "Cache client is missing or not initialized."):
        self.message = message
        super().__init__(self.message)
