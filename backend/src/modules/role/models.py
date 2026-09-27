"""RBAC models: roles, their permissions, and the users assigned to them."""

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from ...infrastructure.database.models import TimestampMixin
from ...infrastructure.database.session import Base
from .constants import PERMISSION_NAME_MAX_LENGTH, ROLE_NAME_MAX_LENGTH
from .permission_registry import is_known_permission

if TYPE_CHECKING:
    from ..user.models import User


class Role(Base, TimestampMixin):
    """Reusable named role that holds a set of permission strings."""

    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
        init=False,
    )
    name: Mapped[str] = mapped_column(
        String(ROLE_NAME_MAX_LENGTH),
        nullable=False,
        unique=True,
    )
    description: Mapped[str | None] = mapped_column(Text, default=None)

    permissions: Mapped[list["RolePermission"]] = relationship(
        "RolePermission",
        back_populates="role",
        lazy="select",
        cascade="all, delete-orphan",
        passive_deletes=True,
        default_factory=list,
        init=False,
    )
    user_roles: Mapped[list["UserRole"]] = relationship(
        "UserRole",
        back_populates="role",
        lazy="select",
        cascade="all, delete-orphan",
        passive_deletes=True,
        default_factory=list,
        init=False,
    )

    def __repr__(self) -> str:
        return self.name


class RolePermission(Base, TimestampMixin):
    """Maps a role to a permission name."""

    __tablename__ = "role_permissions"

    role_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("roles.id", ondelete="CASCADE"),
        primary_key=True,
    )
    permission_name: Mapped[str] = mapped_column(
        String(PERMISSION_NAME_MAX_LENGTH),
        primary_key=True,
    )

    role: Mapped["Role"] = relationship(
        "Role",
        back_populates="permissions",
        lazy="select",
        init=False,
    )

    @validates("permission_name")
    def validate_permission_name(self, key: str, value: str) -> str:
        """Reject permission names that are not registered."""

        if not is_known_permission(value):
            raise ValueError(f"Unknown permission name: {value}")

        return value

    def __repr__(self) -> str:
        return f"{self.role_id}:{self.permission_name}"


class UserRole(Base, TimestampMixin):
    """Maps a user to a role."""

    __tablename__ = "user_roles"

    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("user.id", ondelete="CASCADE"),
        primary_key=True,
    )
    role_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("roles.id", ondelete="CASCADE"),
        primary_key=True,
    )

    user: Mapped["User"] = relationship(
        "User",
        back_populates="user_roles",
        lazy="select",
        init=False,
    )
    role: Mapped["Role"] = relationship(
        "Role",
        back_populates="user_roles",
        lazy="select",
        init=False,
    )

    def __repr__(self) -> str:
        return f"user={self.user_id} role={self.role_id}"
