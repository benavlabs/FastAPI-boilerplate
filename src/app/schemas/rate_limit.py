import uuid as uuid_pkg
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..core.schemas import TimestampSchema


def sanitize_path(path: str) -> str:
    return path.strip("/").replace("/", "_")


class RateLimitBase(BaseModel):
    path: Annotated[str, Field(examples=["users"])]
    limit: Annotated[int, Field(examples=[5])]
    period: Annotated[int, Field(examples=[60])]

    @field_validator("path")
    def validate_and_sanitize_path(cls, v: str) -> str:
        return sanitize_path(v)


class RateLimit(TimestampSchema, RateLimitBase):
    tier_id: uuid_pkg.UUID
    name: Annotated[str | None, Field(default=None, examples=["users:5:60"])]


class RateLimitRead(RateLimitBase):
    id: uuid_pkg.UUID
    tier_id: uuid_pkg.UUID
    name: str


class RateLimitCreate(RateLimitBase):
    model_config = ConfigDict(extra="forbid")

    name: Annotated[str | None, Field(default=None, examples=["api_v1_users:5:60"])]


class RateLimitCreateInternal(RateLimitCreate):
    tier_id: uuid_pkg.UUID


class RateLimitUpdate(BaseModel):
    path: str | None = Field(default=None)
    limit: int | None = None
    period: int | None = None
    name: str | None = None

    @field_validator("path")
    def validate_and_sanitize_path(cls, v: str) -> str:
        return sanitize_path(v) if v is not None else None


class RateLimitUpdateInternal(RateLimitUpdate):
    updated_at: datetime


class RateLimitDelete(BaseModel):
    pass
