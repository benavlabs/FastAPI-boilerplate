import re
from datetime import datetime
from typing import Annotated, ClassVar

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..common.schemas import PartialUpdate, TimestampSchema, not_nullable_columns
from .models import RateLimit as RateLimitModel

_SEGMENT = r"(?:[a-zA-Z0-9_\-.]+|\{[a-zA-Z_][a-zA-Z0-9_]*(?::path)?\})"
PATH_PATTERN = re.compile(rf"^/(?:{_SEGMENT}(?:/{_SEGMENT})*/?)?$")


class RateLimitBase(BaseModel):
    """Base rate limit schema with common attributes."""

    path: Annotated[str, Field(examples=["/api/v1/users"])]
    limit: Annotated[int, Field(examples=[5], gt=0)]
    period: Annotated[int, Field(examples=[60], gt=0)]

    @field_validator("path")
    def validate_path_format(cls, v: str) -> str:
        """Validate path has proper API path format."""
        if not v.startswith("/"):
            raise ValueError("Path must start with a forward slash (/)")

        if not PATH_PATTERN.match(v):
            raise ValueError("Path must be a valid API path format, e.g. /api/v1/users or /api/v1/users/{username}")

        return v


class RateLimit(TimestampSchema, RateLimitBase):
    """Complete rate limit schema."""

    tier_id: int
    name: Annotated[str | None, Field(default=None, examples=["users:5:60"])]


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
    name: Annotated[str | None, Field(default=None, examples=["api_v1_users:5:60"])]


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
    def validate_path_format(cls, v: str | None) -> str | None:
        """Validate path has proper API path format."""
        if v is None:
            return None

        if not v.startswith("/"):
            raise ValueError("Path must start with a forward slash (/)")

        if not PATH_PATTERN.match(v):
            raise ValueError("Path must be a valid API path format, e.g. /api/v1/users or /api/v1/users/{username}")

        return v


class RateLimitUpdateInternal(RateLimitUpdate):
    """Internal schema for rate limit updates."""

    updated_at: datetime


class RateLimitDelete(BaseModel):
    """Schema for deleting a rate limit."""

    pass
