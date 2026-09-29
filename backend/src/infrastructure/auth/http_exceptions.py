"""The CSRF failure the authentication routes answer with.

The general HTTP exceptions live in ``infrastructure.http_exceptions``: core maps
domain errors onto them without depending on this feature.
"""

from fastapi import status
from fastapi.exceptions import HTTPException

__all__ = ["CSRFException"]


class CSRFException(HTTPException):
    """Exception for Cross-Site Request Forgery (CSRF) validation failures.

    Raised when CSRF token validation fails, indicating a potential
    security attack or invalid request from an untrusted source.

    This exception automatically sets the appropriate HTTP status code
    (403 Forbidden) and includes security-relevant headers to help
    clients and security tools identify CSRF-related failures.

    Args:
        detail: Custom error message describing the CSRF failure.
               Defaults to "CSRF token validation failed".

    Note:
        This exception includes the X-CSRF-Error header which:
        - Helps security monitoring tools identify CSRF attacks
        - Allows client-side handling of CSRF errors
        - Provides clear indication of the error type
        - Assists in debugging authentication issues

    Example:
        ```python
        # In a CSRF validation function
        def validate_csrf_token(token: str, session_token: str):
            if not token or token != session_token:
                raise CSRFException("Invalid CSRF token")

        # In an endpoint with CSRF protection
        @app.post("/api/protected-action")
        async def protected_action(csrf_token: str = Form(...)):
            try:
                validate_csrf_token(csrf_token, request.session.get("csrf_token"))
                # Process the protected action
            except CSRFException:
                # Log security event
                logger.warning("CSRF attack attempt detected")
                raise
        ```
    """

    def __init__(self, detail: str = "CSRF token validation failed"):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=detail,
            headers={"X-CSRF-Error": "true"},
        )
