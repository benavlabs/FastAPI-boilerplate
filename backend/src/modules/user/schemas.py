from datetime import datetime
from typing import Annotated, ClassVar

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from ...infrastructure.auth.password_policy import password_policy
from ...wiring.models import UserSchemaExtensions
from ..common.schemas import PartialUpdate, PersistentDeletion, TimestampSchema, not_nullable_columns
from .constants import (
    EMAIL_MAX_LENGTH,
    NAME_MAX_LENGTH,
    USERNAME_MAX_LENGTH,
    USERNAME_PATTERN,
)
from .models import User as UserModel


class UserBase(BaseModel):
    name: Annotated[str, Field(min_length=2, max_length=NAME_MAX_LENGTH, examples=["User Userson"])]
    username: Annotated[
        str,
        Field(min_length=2, max_length=USERNAME_MAX_LENGTH, pattern=USERNAME_PATTERN, examples=["userson"]),
    ]
    email: Annotated[EmailStr, Field(max_length=EMAIL_MAX_LENGTH, examples=["user.userson@example.com"])]


class User(TimestampSchema, UserBase, PersistentDeletion, UserSchemaExtensions):
    """Complete user model with all fields."""

    hashed_password: str
    is_superuser: bool = False
    profile_image_url: Annotated[
        str,
        Field(description="URL of the user's profile image"),
    ] = "https://www.profileimageurl.com"

    google_id: str | None = None
    github_id: str | None = None
    oauth_provider: str | None = None
    email_verified: bool = False
    oauth_created_at: datetime | None = None
    oauth_updated_at: datetime | None = None


class UserProfileRead(BaseModel):
    """Another user's profile: the display fields any signed-in user may see.

    No email address, and none of the fields other features add to the user read
    schemas. The owner reads their own record through ``/users/me``, and a superuser
    through the list and active-and-inactive endpoints.
    """

    id: int
    name: Annotated[str, Field(examples=["User Userson"])]
    username: Annotated[str, Field(examples=["userson"])]
    profile_image_url: str


class UserRead(UserSchemaExtensions):
    """Schema for reading user data, excludes sensitive information.

    The input rules live on the create and update schemas. A read schema that
    repeated them would refuse rows the app itself writes, such as the short name
    a provider login can leave behind, and turn them into a failed response.
    """

    id: int
    name: Annotated[str, Field(examples=["User Userson"])]
    username: Annotated[str, Field(examples=["userson"])]
    email: Annotated[str, Field(examples=["user.userson@example.com"])]
    profile_image_url: str
    is_deleted: bool = False
    is_superuser: bool = False
    email_verified: bool = False
    oauth_provider: str | None = None


class UserCreate(UserBase):
    """Schema for creating a new user.

    Signing up never sets the OAuth identifiers or ``email_verified``: a self-declared
    verified address would pre-claim it, and crudauth links a provider login to an
    existing account by verified email. Those fields belong to
    ``UserCreateInternal``, which only server-side code builds.
    """

    password: password_policy.body_field()  # type: ignore[valid-type]

    model_config = ConfigDict(extra="forbid")


class UserCreateInternal(UserBase):
    """Internal schema for user creation with hashed password."""

    hashed_password: str
    google_id: str | None = None
    github_id: str | None = None
    oauth_provider: str | None = None
    email_verified: bool = False
    oauth_created_at: datetime | None = None
    oauth_updated_at: datetime | None = None


class UserUpdate(PartialUpdate):
    """Schema for updating user data."""

    model_config = ConfigDict(extra="forbid")

    NOT_NULLABLE: ClassVar[tuple[str, ...]] = not_nullable_columns(UserModel)

    name: Annotated[
        str | None,
        Field(min_length=2, max_length=NAME_MAX_LENGTH, examples=["User Userberg"]),
    ] = None
    username: Annotated[
        str | None,
        Field(
            min_length=2,
            max_length=USERNAME_MAX_LENGTH,
            pattern=USERNAME_PATTERN,
            examples=["userberg"],
        ),
    ] = None
    email: Annotated[
        EmailStr | None,
        Field(max_length=EMAIL_MAX_LENGTH, examples=["user.userberg@example.com"]),
    ] = None
    profile_image_url: Annotated[
        str | None,
        Field(
            pattern=r"^(https?|ftp)://[^\s/$.?#].[^\s]*$",
            examples=["https://www.profileimageurl.com"],
        ),
    ] = None


class UserSelfUpdate(UserUpdate):
    """Schema for the fields a user may change on their own account."""

    current_password: Annotated[
        str | None,
        Field(exclude=True, description="Required when the email changes"),
    ] = None


class UserAdminUpdate(UserUpdate):
    """Schema for updates only an administrator may make.

    The OAuth identifiers and the verification flag decide who a provider login
    resolves to, so they are not part of the public profile update.
    """

    google_id: str | None = None
    github_id: str | None = None
    oauth_provider: str | None = None
    email_verified: bool | None = None
    oauth_updated_at: datetime | None = None


class UserUpdateInternal(UserAdminUpdate):
    """Internal schema for user updates."""

    updated_at: datetime


class UserDelete(BaseModel):
    """Schema for soft-deleting a user."""

    model_config = ConfigDict(extra="forbid")

    is_deleted: bool
    deleted_at: datetime


class UserAnonymize(UserSchemaExtensions):
    """Schema for GDPR/LGPD compliant user anonymization.

    This schema includes all fields that need to be updated during
    the user anonymization process for privacy compliance.
    """

    model_config = ConfigDict(extra="forbid")

    name: str
    username: str
    hashed_password: str | None = None
    profile_image_url: str | None = None
    is_superuser: bool = False
    google_id: str | None = None
    github_id: str | None = None
    oauth_provider: str | None = None
    email_verified: bool = False
    oauth_created_at: datetime | None = None
    oauth_updated_at: datetime | None = None


class UserRestoreDeleted(BaseModel):
    """Schema for restoring a deleted user."""

    is_deleted: bool
