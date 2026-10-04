from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from ...infrastructure.database.models import SoftDeleteMixin, TimestampMixin
from ...infrastructure.database.session import Base
from ...wiring.models import UserModelExtensions
from .constants import EMAIL_MAX_LENGTH, NAME_MAX_LENGTH, USERNAME_MAX_LENGTH


class User(Base, TimestampMixin, SoftDeleteMixin, UserModelExtensions):
    """User model representing application users.

    Other features add to it through ``UserModelExtensions`` in the wiring: rbac
    contributes ``user_roles``, and the tiers feature ``tier_id`` and ``tier``.
    """

    __tablename__ = "user"

    id: Mapped[int] = mapped_column(
        "id",
        autoincrement=True,
        nullable=False,
        primary_key=True,
        init=False,
    )

    name: Mapped[str] = mapped_column(String(NAME_MAX_LENGTH))
    username: Mapped[str] = mapped_column(String(USERNAME_MAX_LENGTH), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(EMAIL_MAX_LENGTH), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(100))

    profile_image_url: Mapped[str] = mapped_column(String, default="https://profileimageurl.com")

    is_superuser: Mapped[bool] = mapped_column(default=False)

    google_id: Mapped[str | None] = mapped_column(String(50), unique=True, index=True, default=None)
    github_id: Mapped[str | None] = mapped_column(String(50), unique=True, index=True, default=None)
    oauth_provider: Mapped[str | None] = mapped_column(String(20), default=None)
    email_verified: Mapped[bool] = mapped_column(default=False)
    oauth_created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    oauth_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

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
