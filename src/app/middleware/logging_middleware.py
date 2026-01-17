"""
Request/Response Logging Middleware for FastAPI.

Logs incoming requests and outgoing responses with timing information.
Configurable via LoggingSettings to include/exclude request/response bodies.
"""

import logging
import time
import uuid

from fastapi import FastAPI, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

logger = logging.getLogger(__name__)


class LoggingMiddleware(BaseHTTPMiddleware):
    """Middleware to log incoming requests and outgoing responses.

    Features:
    - Logs request method, path, query params, and client IP
    - Logs response status code, content length, and processing time
    - Optionally logs request/response bodies (configurable)
    - Assigns a unique request ID for correlation
    - Excludes configurable paths from logging (e.g., health checks)

    Parameters
    ----------
    app : FastAPI
        The FastAPI application instance.
    log_request_body : bool, optional
        Whether to log request bodies. Default: False
    log_response_body : bool, optional
        Whether to log response bodies. Default: False
    exclude_paths : list[str], optional
        Paths to exclude from logging. Default: ["/health", "/metrics"]
    """

    def __init__(
        self,
        app: FastAPI,
        log_request_body: bool = False,
        log_response_body: bool = False,
        exclude_paths: list[str] | None = None,
    ) -> None:
        super().__init__(app)
        self.log_request_body = log_request_body
        self.log_response_body = log_response_body
        self.exclude_paths = exclude_paths or ["/health", "/metrics", "/favicon.ico"]

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """Process and log the request/response cycle.

        Parameters
        ----------
        request : Request
            The incoming HTTP request.
        call_next : RequestResponseEndpoint
            The next middleware or route handler.

        Returns
        -------
        Response
            The response from the route handler.
        """
        # Skip logging for excluded paths
        if any(request.url.path.startswith(path) for path in self.exclude_paths):
            return await call_next(request)

        # Generate unique request ID
        request_id = str(uuid.uuid4())[:8]

        # Start timing
        start_time = time.perf_counter()

        # Log incoming request
        await self._log_request(request, request_id)

        # Process request
        try:
            response = await call_next(request)
        except Exception as exc:
            # Log exception and re-raise (will be caught by exception middleware)
            process_time = time.perf_counter() - start_time
            logger.error(f"[{request_id}] Request failed after {process_time:.3f}s: {type(exc).__name__}: {exc}")
            raise

        # Calculate processing time
        process_time = time.perf_counter() - start_time

        # Log outgoing response
        self._log_response(request, response, request_id, process_time)

        # Add request ID and timing headers to response
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Process-Time"] = f"{process_time:.3f}s"

        return response

    async def _log_request(self, request: Request, request_id: str) -> None:
        """Log details of the incoming request.

        Parameters
        ----------
        request : Request
            The incoming HTTP request.
        request_id : str
            Unique identifier for this request.
        """
        # Get client IP (handle proxied requests)
        client_ip = request.client.host if request.client else "unknown"
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            client_ip = forwarded_for.split(",")[0].strip()

        # Build log message
        query_string = f"?{request.url.query}" if request.url.query else ""
        user_agent = request.headers.get("User-Agent", "unknown")[:50]

        logger.info(
            f"[{request_id}] --> {request.method} {request.url.path}{query_string} from {client_ip} ({user_agent})"
        )

        # Optionally log request body
        if self.log_request_body and request.method in ("POST", "PUT", "PATCH"):
            try:
                body = await request.body()
                if body:
                    # Limit body size in logs
                    body_str = body.decode("utf-8")[:1000]
                    logger.debug(f"[{request_id}] Request body: {body_str}")
            except Exception as e:
                logger.debug(f"[{request_id}] Could not read request body: {e}")

    def _log_response(
        self,
        request: Request,
        response: Response,
        request_id: str,
        process_time: float,
    ) -> None:
        """Log details of the outgoing response.

        Parameters
        ----------
        request : Request
            The original request.
        response : Response
            The outgoing response.
        request_id : str
            Unique identifier for this request.
        process_time : float
            Time taken to process the request in seconds.
        """
        content_length = response.headers.get("Content-Length", "unknown")

        # Determine log level based on status code
        status_code = response.status_code
        if status_code >= 500:
            log_func = logger.error
        elif status_code >= 400:
            log_func = logger.warning
        else:
            log_func = logger.info

        log_func(
            f"[{request_id}] <-- {request.method} {request.url.path} "
            f"{status_code} ({content_length} bytes) in {process_time:.3f}s"
        )


def create_logging_middleware() -> type[LoggingMiddleware]:
    """Factory function to create LoggingMiddleware with settings from config.

    Returns
    -------
    type[LoggingMiddleware]
        Configured LoggingMiddleware class ready to be added to the app.
    """
    return LoggingMiddleware
