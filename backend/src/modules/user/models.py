from typing import TYPE_CHECKING

from crudauth.models import AuthUserMixin
from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ...infrastructure.database.models import SoftDeleteMixin
from ...infrastructure.database.session import Base

if TYPE_CHECKING:
    from ..tier.models import Tier


class User(Base, SoftDeleteMixin, AuthUserMixin):
    """User model representing application users."""

    __tablename__ = "user"

    name: Mapped[str] = mapped_column(String(30), kw_only=True)
    profile_image_url: Mapped[str] = mapped_column(String, default="https://profileimageurl.com")

    tier_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("tiers.id"),
        index=True,
        default=None,
    )

    tier: Mapped["Tier | None"] = relationship("Tier", back_populates="users", lazy="selectin", init=False)

    def __repr__(self) -> str:
        return f"{self.name} ({self.email})"
