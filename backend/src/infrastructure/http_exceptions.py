"""The HTTP exceptions the app answers with.

Core owns these: the error handler maps every domain error onto one, whatever
features a project selected.
"""

from fastapi.exceptions import HTTPException
from fastcrud.exceptions.http_exceptions import (
    BadRequestException,
    DuplicateValueException,
    ForbiddenException,
    NotFoundException,
    RateLimitException,
    UnauthorizedException,
    UnprocessableEntityException,
)

__all__ = [
    "BadRequestException",
    "DuplicateValueException",
    "ForbiddenException",
    "HTTPException",
    "NotFoundException",
    "RateLimitException",
    "UnauthorizedException",
    "UnprocessableEntityException",
]
