"""
Middleware package for FastAPI application.

This package contains custom middleware classes for:
- Exception handling with consistent JSON responses
- Request/Response logging
- Client-side cache headers
"""

from .client_cache_middleware import ClientCacheMiddleware
from .exception_handler_middleware import ExceptionHandlerMiddleware, setup_exception_handlers
from .logging_middleware import LoggingMiddleware

__all__ = [
    "ClientCacheMiddleware",
    "ExceptionHandlerMiddleware",
    "LoggingMiddleware",
    "setup_exception_handlers",
]
