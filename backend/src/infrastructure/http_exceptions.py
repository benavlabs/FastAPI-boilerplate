"""The HTTP exceptions the app answers with.

Core owns these: the error handler maps every domain error onto one, whatever
features a project selected.
"""

from fastapi.exceptions import HTTPException
from fastcrud.exceptions.http_exceptions import (
    BadRequestException,
    CustomException,
    DuplicateValueException,
    ForbiddenException,
    NotFoundException,
    RateLimitException,
    UnauthorizedException,
    UnprocessableEntityException,
)


class ConflictException(CustomException):
    """A request that collides with a row already there: ``409 Conflict``."""

    def __init__(self, detail: str | None = None) -> None:
        super().__init__(status_code=409, detail=detail)


__all__ = [
    "BadRequestException",
    "ConflictException",
    "DuplicateValueException",
    "ForbiddenException",
    "HTTPException",
    "NotFoundException",
    "RateLimitException",
    "UnauthorizedException",
    "UnprocessableEntityException",
]
