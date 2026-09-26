from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from ...infrastructure.database.models import TimestampMixin
from ...infrastructure.database.session import Base
from .permission_registry import all_permissions

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
        String(50),
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
        init=False,
    )
    permission_name: Mapped[str] = mapped_column(
        String(100),
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

        if value not in all_permissions():
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
        init=False,
    )
    role_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("roles.id", ondelete="CASCADE"),
        primary_key=True,
        init=False,
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