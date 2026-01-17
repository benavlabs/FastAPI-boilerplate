"""
Standard API response schema for consistent JSON responses.

All API responses follow this structure:
- data: The actual response payload (can be any type or None)
- isSuccess: Boolean indicating if the request was successful
- message: Human-readable message describing the result
- statusCode: HTTP status code matching the response status
"""

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class APIResponse(BaseModel, Generic[T]):
    """Generic API response wrapper for consistent JSON structure.

    Attributes
    ----------
    data : T | None
        The response payload. Can be any type (object, list, etc.) or None for error responses.
    isSuccess : bool
        Indicates whether the request was processed successfully.
    message : str
        Human-readable message describing the result or error.
    statusCode : int
        HTTP status code matching the response status.

    Examples
    --------
    Success response:
        >>> APIResponse(data={"id": 1}, isSuccess=True, message="User created", statusCode=201)

    Error response:
        >>> APIResponse(data=None, isSuccess=False, message="Not found", statusCode=404)
    """

    data: T | None = Field(default=None, description="Response payload")
    isSuccess: bool = Field(..., description="Whether the request succeeded")
    message: str = Field(..., description="Human-readable result message")
    statusCode: int = Field(..., description="HTTP status code", ge=100, le=599)

    model_config = {
        "json_schema_extra": {
            "example": {
                "data": {"id": 1, "name": "example"},
                "isSuccess": True,
                "message": "Request successful",
                "statusCode": 200,
            }
        }
    }


class ValidationErrorDetail(BaseModel):
    """Detail for a single validation error."""

    loc: list[str | int] = Field(..., description="Location of the error (field path)")
    msg: str = Field(..., description="Error message")
    type: str = Field(..., description="Error type identifier")


class ValidationErrorResponse(APIResponse[list[ValidationErrorDetail]]):
    """Specialized response for validation errors (422)."""

    pass


# Helper functions for creating responses
def success_response(
    data: Any = None,
    message: str = "Request successful",
    status_code: int = 200,
) -> APIResponse:
    """Create a success response."""
    return APIResponse(
        data=data,
        isSuccess=True,
        message=message,
        statusCode=status_code,
    )


def error_response(
    message: str,
    status_code: int = 400,
    data: Any = None,
) -> APIResponse:
    """Create an error response."""
    return APIResponse(
        data=data,
        isSuccess=False,
        message=message,
        statusCode=status_code,
    )
