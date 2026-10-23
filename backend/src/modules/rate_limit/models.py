from sqlalchemy import ForeignKey, Index, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from ...infrastructure.database import Base
from ...infrastructure.database.models import SoftDeleteMixin, TimestampMixin


class RateLimit(Base, TimestampMixin, SoftDeleteMixin):
    """Rate limit configuration for API endpoints."""

    __tablename__ = "rate_limits"

    id: Mapped[int] = mapped_column(
        "id",
        autoincrement=True,
        nullable=False,
        primary_key=True,
        init=False,
    )
    tier_id: Mapped[int] = mapped_column(ForeignKey("tiers.id"), index=True)
    name: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    path: Mapped[str] = mapped_column(String, nullable=False)
    limit: Mapped[int] = mapped_column(Integer, nullable=False)
    period: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (
        Index(
            "uq_rate_limits_tier_path",
            "tier_id",
            "path",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
    )
