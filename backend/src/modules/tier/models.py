from typing import TYPE_CHECKING

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ...infrastructure.database.models import SoftDeleteMixin, TimestampMixin
from ...infrastructure.database.session import Base

if TYPE_CHECKING:
    from ..user.models import User


class Tier(Base, TimestampMixin, SoftDeleteMixin):
    """Tier model — bare model for user categorization. No business logic, no pricing."""

    __tablename__ = "tiers"

    id: Mapped[int] = mapped_column(
        "id",
        autoincrement=True,
        nullable=False,
        primary_key=True,
        init=False,
    )
    name: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text, default=None)

    users: Mapped[list["User"]] = relationship("User", back_populates="tier", lazy="select", default_factory=list, init=False)

    def __repr__(self) -> str:
        return self.name
