from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from ..core.db.database import Base
from ..core.db.models import TimestampMixin, UUIDMixin


class Tier(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "tier"

    name: Mapped[str] = mapped_column(String, nullable=False, unique=True)

