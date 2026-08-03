from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from ..common.schemas import PersistentDeletion, TimestampSchema

# Kept in one place because every user schema has to agree with the ``username``
# column (``String(32)``) *and* with what crudauth's OAuth username generator
# emits: it caps at 32 and sanitizes to lowercase alphanumerics plus underscores.
# A narrower rule here does not reject the signup - crudauth writes the row
# directly - it makes the resulting user unreadable through ``UserRead``.
USERNAME_MAX_LENGTH = 32
USERNAME_PATTERN = r"^[a-z0-9_]+$"


class UserBase(BaseModel):
    name: Annotated[str, Field(min_length=2, max_length=30, examples=["User Userson"])]
    username: Annotated[
        str,
        Field(min_length=2, max_length=USERNAME_MAX_LENGTH, pattern=USERNAME_PATTERN, examples=["userson"]),
    ]
    email: Annotated[EmailStr, Field(examples=["user.userson@example.com"])]


class User(TimestampSchema, UserBase, PersistentDeletion):
    """Complete user model with all fields."""

    hashed_password: str
    is_superuser: bool = False
    profile_image_url: Annotated[
        str,
        Field(
            default="https://www.profileimageurl.com",
            description="URL of the user's profile image",
        ),
    ]
    tier_id: int | None = None

    google_id: str | None = None
    github_id: str | None = None
    zitadel_id: str | None = None
    oauth_provider: str | None = None
    email_verified: bool = False
    oauth_created_at: datetime | None = None
    oauth_updated_at: datetime | None = None


class UserRead(BaseModel):
    """Schema for reading user data, excludes sensitive information."""

    id: int
    name: Annotated[str, Field(min_length=2, max_length=30, examples=["User Userson"])]
    username: Annotated[
        str,
        Field(min_length=2, max_length=USERNAME_MAX_LENGTH, pattern=USERNAME_PATTERN, examples=["userson"]),
    ]
    email: Annotated[EmailStr, Field(examples=["user.userson@example.com"])]
    profile_image_url: str
    is_deleted: bool = False
    tier_id: int | None
    is_superuser: bool = False
    email_verified: bool = False
    oauth_provider: str | None = None


class UserCreate(UserBase):
    """Schema for creating a new user."""

    password: Annotated[
        str,
        Field(
            min_length=8,
            description=(
                "Password must be at least 8 characters long and include a number,"
                "uppercase letter, lowercase letter, and special character"
            ),
            examples=["Str1ngst!"],
            pattern=r"^.{8,}|[0-9]+|[A-Z]+|[a-z]+|[^a-zA-Z0-9]+$",
        ),
    ]
    google_id: str | None = None
    github_id: str | None = None
    zitadel_id: str | None = None
    oauth_provider: str | None = None
    email_verified: bool = False
    oauth_created_at: datetime | None = None
    oauth_updated_at: datetime | None = None

    model_config = ConfigDict(extra="forbid")


class UserCreateInternal(UserBase):
    """Internal schema for user creation with hashed password."""

    hashed_password: str
    google_id: str | None = None
    github_id: str | None = None
    zitadel_id: str | None = None
    oauth_provider: str | None = None
    email_verified: bool = False
    oauth_created_at: datetime | None = None
    oauth_updated_at: datetime | None = None


class UserUpdate(BaseModel):
    """Schema for updating user data."""

    model_config = ConfigDict(extra="forbid")

    name: Annotated[
        str | None,
        Field(min_length=2, max_length=30, examples=["User Userberg"], default=None),
    ]
    username: Annotated[
        str | None,
        Field(
            min_length=2,
            max_length=USERNAME_MAX_LENGTH,
            pattern=USERNAME_PATTERN,
            examples=["userberg"],
            default=None,
        ),
    ]
    email: Annotated[EmailStr | None, Field(examples=["user.userberg@example.com"], default=None)]
    profile_image_url: Annotated[
        str | None,
        Field(
            pattern=r"^(https?|ftp)://[^\s/$.?#].[^\s]*$",
            examples=["https://www.profileimageurl.com"],
            default=None,
        ),
    ]
    google_id: str | None = None
    github_id: str | None = None
    zitadel_id: str | None = None
    oauth_provider: str | None = None
    email_verified: bool | None = None
    oauth_updated_at: datetime | None = None


class UserUpdateInternal(UserUpdate):
    """Internal schema for user updates."""

    updated_at: datetime


class UserTierUpdate(BaseModel):
    """Schema for updating a user's tier."""

    tier_id: int


class UserDelete(BaseModel):
    """Schema for soft-deleting a user."""

    model_config = ConfigDict(extra="forbid")

    is_deleted: bool
    deleted_at: datetime


class UserAnonymize(BaseModel):
    """Schema for GDPR/LGPD compliant user anonymization.

    This schema includes all fields that need to be updated during
    the user anonymization process for privacy compliance.
    """

    model_config = ConfigDict(extra="forbid")

    name: str
    username: str
    hashed_password: str | None = None
    profile_image_url: str | None = None
    tier_id: int | None = None
    is_superuser: bool = False
    # Every provider link has to be listed here, not just nulled at the call site:
    # a field absent from this schema cannot be cleared, so the provider account
    # would keep resolving to the anonymized row on the next login.
    google_id: str | None = None
    github_id: str | None = None
    zitadel_id: str | None = None
    oauth_provider: str | None = None
    email_verified: bool = False
    oauth_created_at: datetime | None = None
    oauth_updated_at: datetime | None = None


class UserRestoreDeleted(BaseModel):
    """Schema for restoring a deleted user."""

    is_deleted: bool
