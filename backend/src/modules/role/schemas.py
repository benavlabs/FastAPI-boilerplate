from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field

from ..common.schemas import TimestampSchema


class RoleBase(BaseModel):
    """Base role schema."""

    name: Annotated[
        str,
        Field(
            description="Unique role name",
            examples=["editor", "support"],
            min_length=1,
            max_length=50,
        ),
    ]


class Role(TimestampSchema, RoleBase):
    """Complete role schema with timestamps."""

    pass


class RoleSelect(BaseModel):
    """Minimal schema for selecting required role fields."""

    id: int
    name: str


class RoleRead(RoleBase):
    """Schema for reading a role."""

    id: int
    created_at: datetime
    description: str | None = None
    is_deleted: bool = False
    permissions: list[str] = Field(default_factory=list)


class RoleCreate(RoleBase):
    """Schema for creating a role."""

    description: Annotated[
        str | None,
        Field(description="Role description", max_length=255, default=None),
    ]


class RoleCreateInternal(RoleCreate):
    """Internal schema for role creation."""

    pass


class RoleUpdate(BaseModel):
    """Schema for updating a role."""

    name: Annotated[
        str | None,
        Field(description="Unique role name", min_length=1, max_length=50, default=None),
    ]
    description: Annotated[
        str | None,
        Field(description="Role description", max_length=255, default=None),
    ]


class RoleUpdateInternal(RoleUpdate):
    """Internal schema for role updates."""

    updated_at: datetime


class RolePermissionCreate(BaseModel):
    """Assign a permission name to a role."""

    role_id: int
    permission_name: Annotated[str, Field(min_length=1, max_length=100)]


class RolePermissionRead(BaseModel):
    """Read a role-permission assignment."""

    id: int
    role_id: int
    permission_name: str
    created_at: datetime


class UserRoleCreate(BaseModel):
    """Assign a role to a user."""

    user_id: int
    role_id: int


class UserRoleRead(BaseModel):
    """Read a user-role assignment."""

    id: int
    user_id: int
    role_id: int
    created_at: datetime