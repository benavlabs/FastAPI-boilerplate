"""What a role looks like coming in and going out."""

from datetime import datetime
from typing import Annotated, Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ...infrastructure.permissions import registered_permissions
from ..common.schemas import PartialUpdate, not_nullable_columns
from .constants import ROLE_NAME_MAX_LENGTH
from .models import Role as RoleModel

RoleName = Annotated[str, Field(min_length=1, max_length=ROLE_NAME_MAX_LENGTH, examples=["editor"])]
RoleDescription = Annotated[str | None, Field(max_length=500, examples=["Edits other people's profiles"])]


class RolePermissions(BaseModel):
    """The permissions a role carries."""

    model_config = ConfigDict(extra="forbid")

    permissions: list[str] = Field(default_factory=list, examples=[["user.read", "user.update"]])

    @field_validator("permissions")
    @classmethod
    def _registered(cls, names: list[str]) -> list[str]:
        return registered_permissions(names)


class RoleCreate(RolePermissions):
    """A new role, and what it carries."""

    name: RoleName
    description: RoleDescription = None


class RoleUpdate(PartialUpdate):
    """A change to a role's name or description; its permissions have their own route."""

    model_config = ConfigDict(extra="forbid")

    NOT_NULLABLE: ClassVar[tuple[str, ...]] = not_nullable_columns(RoleModel)

    name: RoleName | None = None
    description: RoleDescription = None


class RoleRead(BaseModel):
    """A role as the API answers it."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None = None
    permissions: list[str] = Field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @classmethod
    def of(cls, role: Any, permissions: list[str]) -> "RoleRead":
        """The role row, with the permission names it carries."""
        return cls(
            id=role.id,
            name=role.name,
            description=role.description,
            permissions=sorted(permissions),
            created_at=role.created_at,
            updated_at=role.updated_at,
        )
