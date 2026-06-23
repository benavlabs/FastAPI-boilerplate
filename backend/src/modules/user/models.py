from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ...infrastructure.database.models import SoftDeleteMixin, TimestampMixin
from ...infrastructure.database.session import Base

if TYPE_CHECKING:
    from ..tier.models import Tier


class User(Base, TimestampMixin, SoftDeleteMixin):
    """User model representing application users."""

    __tablename__ = "user"

    id: Mapped[int] = mapped_column(
        "id",
        autoincrement=True,
        nullable=False,
        unique=True,
        primary_key=True,
        init=False,
    )

    name: Mapped[str] = mapped_column(String(30))
    username: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(100))

    profile_image_url: Mapped[str] = mapped_column(String, default="https://profileimageurl.com")

    tier_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("tiers.id"),
        index=True,
        default=None,
    )

    is_superuser: Mapped[bool] = mapped_column(default=False)

    google_id: Mapped[str | None] = mapped_column(String(50), unique=True, index=True, default=None)
    github_id: Mapped[str | None] = mapped_column(String(50), unique=True, index=True, default=None)
    oauth_provider: Mapped[str | None] = mapped_column(String(20), default=None)
    email_verified: Mapped[bool] = mapped_column(default=False)
    oauth_created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    oauth_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    tier: Mapped["Tier | None"] = relationship("Tier", back_populates="users", lazy="selectin", init=False)

    @property
    def is_active(self) -> bool:
        """Derived active flag for crudauth: a soft-deleted user is inactive.

        ``is_deleted`` stays the single source of truth; crudauth reads ``is_active``
        to gate authentication, so this maps the contract onto the existing column
        without adding a new one.
        """
        return not self.is_deleted

    def __repr__(self) -> str:
        return f"{self.name} ({self.email})"
