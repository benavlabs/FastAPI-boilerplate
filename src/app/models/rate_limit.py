import uuid as uuid_pkg

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from ..core.db.database import Base
from ..core.db.models import TimestampMixin, UUIDMixin


class RateLimit(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "rate_limit"

    tier_id: Mapped[uuid_pkg.UUID] = mapped_column(ForeignKey("tier.uuid"), index=True)
    name: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    path: Mapped[str] = mapped_column(String, nullable=False)
    limit: Mapped[int] = mapped_column(Integer, nullable=False)
    period: Mapped[int] = mapped_column(Integer, nullable=False)
