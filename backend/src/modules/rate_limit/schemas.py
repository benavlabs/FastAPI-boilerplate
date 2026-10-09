import re
from datetime import datetime
from typing import Annotated, ClassVar

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..common.schemas import PartialUpdate, TimestampSchema, not_nullable_columns
from .models import RateLimit as RateLimitModel

PATH_CONVERTERS = ("str", "path", "int", "float", "uuid")

_LITERAL = r"[a-zA-Z0-9_\-.~]+"
_PARAMETER = rf"\{{[a-zA-Z_][a-zA-Z0-9_]*(?::(?:{'|'.join(PATH_CONVERTERS)}))?\}}"
_SEGMENT = rf"(?:{_LITERAL}{_PARAMETER}{_LITERAL}|{_LITERAL}{_PARAMETER}|{_PARAMETER}{_LITERAL}|{_PARAMETER}|{_LITERAL})"
PATH_PATTERN = re.compile(rf"/(?:{_SEGMENT}(?:/{_SEGMENT})*/?)?")

PATH_FORMAT_REFUSAL = (
    "Path must be a route template the router declares, such as /api/v1/users/, "
    "/api/v1/users/{username}, /api/v1/items/{id:int} or /files/{filepath:path}"
)


def validated_path(value: str) -> str:
    """Return ``value`` when it reads as a route template.

    A segment is literal text, one parameter with an optional Starlette converter, or
    literal text around one parameter.

    Raises:
        ValueError: ``value`` does not start with ``/``, or is not a route template.
    """
    if not value.startswith("/"):
        raise ValueError("Path must start with a forward slash (/)")

    if not PATH_PATTERN.fullmatch(value):
        raise ValueError(PATH_FORMAT_REFUSAL)

    return value


class RateLimitBase(BaseModel):
    """Base rate limit schema with common attributes."""

    path: Annotated[str, Field(examples=["/api/v1/users/"])]
    limit: Annotated[int, Field(examples=[5], gt=0)]
    period: Annotated[int, Field(examples=[60], gt=0)]

    _path_is_a_template = field_validator("path")(validated_path)


class RateLimit(TimestampSchema, RateLimitBase):
    """Complete rate limit schema."""

    tier_id: int
    name: Annotated[str | None, Field(examples=["users:5:60"])] = None


class RateLimitSelect(BaseModel):
    """Minimal schema for selecting only required rate limit fields."""

    limit: int
    period: int


class RateLimitRead(BaseModel):
    """Schema for reading rate limit data.

    The path format and the positive bounds belong to the create and update
    schemas. Repeating them here would answer 500 for a row the app already
    holds, such as one stored before the format was tightened.
    """

    id: int
    tier_id: int
    name: str
    path: str
    limit: int
    period: int
    is_deleted: bool = False


class RateLimitCreate(RateLimitBase):
    """Schema for creating a new rate limit."""

    model_config = ConfigDict(extra="forbid")
    name: Annotated[str | None, Field(examples=["api_v1_users:5:60"])] = None


class RateLimitCreateInternal(RateLimitCreate):
    """Internal schema for rate limit creation."""

    tier_id: int


class RateLimitUpdate(PartialUpdate):
    """Schema for updating rate limit information."""

    NOT_NULLABLE: ClassVar[tuple[str, ...]] = not_nullable_columns(RateLimitModel)

    path: str | None = Field(default=None)
    limit: int | None = Field(default=None, gt=0)
    period: int | None = Field(default=None, gt=0)
    name: str | None = None

    @field_validator("path")
    @classmethod
    def _path_is_a_template(cls, value: str | None) -> str | None:
        """Validate the path the same way creating one does, when one is given."""
        return None if value is None else validated_path(value)


class RateLimitUpdateInternal(RateLimitUpdate):
    """Internal schema for rate limit updates."""

    updated_at: datetime


class RateLimitDelete(BaseModel):
    """Schema for deleting a rate limit."""

    pass
