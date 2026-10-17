"""What the rbac feature adds to the user model.

Listed in ``wiring.models``, so ``User`` gains ``user_roles`` without the user
module knowing that roles exist.
"""

from typing import TYPE_CHECKING

from sqlalchemy.orm import Mapped, MappedAsDataclass, declared_attr, relationship

if TYPE_CHECKING:
    from .models import UserRole


class UserRoleColumns(MappedAsDataclass):
    """The ``User.user_roles`` relationship."""

    @declared_attr
    def user_roles(cls) -> Mapped[list["UserRole"]]:
        return relationship(
            "UserRole",
            back_populates="user",
            lazy="select",
            cascade="all, delete-orphan",
            passive_deletes=True,
            default_factory=list,
            init=False,
        )
