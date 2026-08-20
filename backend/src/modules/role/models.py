from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ...infrastructure.database.models import SoftDeleteMixin, TimestampMixin
from ...infrastructure.database.session import Base

if TYPE_CHECKING:
    from ..user.models import User


class Role(Base, TimestampMixin, SoftDeleteMixin):
    """Reusable named role that holds a set of permission strings."""

    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(
        "id",
        autoincrement=True,
        nullable=False,
        unique=True,
        primary_key=True,
        init=False,
    )
    name: Mapped[str] = mapped_column(String(50), nullable=False, unique=True, index=True)
    description: Mapped[str | None] = mapped_column(String(255), default=None)

    permissions: Mapped[list["RolePermission"]] = relationship(
        "RolePermission",
        back_populates="role",
        lazy="selectin",
        default_factory=list,
        init=False,
    )
    user_roles: Mapped[list["UserRole"]] = relationship(
        "UserRole",
        back_populates="role",
        lazy="selectin",
        default_factory=list,
        init=False,
    )

    def __repr__(self) -> str:
        return self.name


class RolePermission(Base, TimestampMixin):
    """Maps a role to a permission name constant."""

    __tablename__ = "role_permission"
    __table_args__ = (UniqueConstraint("role_id", "permission_name", name="uq_role_permission"),)

    id: Mapped[int] = mapped_column(
        "id",
        autoincrement=True,
        nullable=False,
        unique=True,
        primary_key=True,
        init=False,
    )
    role_id: Mapped[int] = mapped_column(Integer, ForeignKey("roles.id"), index=True)
    permission_name: Mapped[str] = mapped_column(String(100), index=True)

    role: Mapped["Role"] = relationship("Role", back_populates="permissions", lazy="selectin", init=False)

    def __repr__(self) -> str:
        return f"{self.role_id}:{self.permission_name}"


class UserRole(Base, TimestampMixin):
    """Maps a user to a role."""

    __tablename__ = "user_role"
    __table_args__ = (UniqueConstraint("user_id", "role_id", name="uq_user_role"),)

    id: Mapped[int] = mapped_column(
        "id",
        autoincrement=True,
        nullable=False,
        unique=True,
        primary_key=True,
        init=False,
    )
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("user.id"), index=True)
    role_id: Mapped[int] = mapped_column(Integer, ForeignKey("roles.id"), index=True)

    user: Mapped["User"] = relationship("User", back_populates="user_roles", lazy="selectin", init=False)
    role: Mapped["Role"] = relationship("Role", back_populates="user_roles", lazy="selectin", init=False)

    def __repr__(self) -> str:
        return f"user={self.user_id} role={self.role_id}"