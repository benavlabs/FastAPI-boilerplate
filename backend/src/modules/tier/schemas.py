from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field

from ..common.schemas import TimestampSchema


class TierBase(BaseModel):
    """Base tier schema with common attributes."""

    name: Annotated[
        str,
        Field(
            description="Name of the tier",
            examples=["free", "basic", "pro", "enterprise"],
            min_length=1,
            max_length=50,
        ),
    ]


class Tier(TimestampSchema, TierBase):
    """Complete tier schema with timestamps."""

    pass


class TierSelect(BaseModel):
    """Minimal schema for selecting only required tier fields."""

    id: int
    name: str


class TierRead(TierBase):
    """Schema for reading tier data."""

    id: int
    created_at: datetime
    description: str | None = None
    is_deleted: bool = False


class TierCreate(TierBase):
    """Schema for creating a new tier."""

    description: Annotated[
        str | None,
        Field(
            description="Description of the tier",
            max_length=500,
            default=None,
        ),
    ]


class TierCreateInternal(TierCreate):
    """Internal schema for tier creation."""

    pass


class TierUpdate(BaseModel):
    """Schema for updating tier information."""

    name: Annotated[
        str | None,
        Field(
            description="Name of the tier",
            min_length=1,
            max_length=50,
            default=None,
        ),
    ]
    description: Annotated[
        str | None,
        Field(
            description="Description of the tier",
            max_length=500,
            default=None,
        ),
    ]


class TierUpdateInternal(TierUpdate):
    """Internal schema for tier updates."""

    updated_at: datetime


class TierDelete(BaseModel):
    """Schema for deleting a tier."""

    pass


class UserTierUpdate(BaseModel):
    """The payload for putting a user on a tier."""

    tier_id: int
