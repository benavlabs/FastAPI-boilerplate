import uuid as uuid_pkg
from typing import Any

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..core.db.database import Base
from ..core.db.models import TimestampMixin, UUIDMixin


class Setting(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "setting"

    scope: Mapped[str] = mapped_column(String(10), index=True)
    user_id: Mapped[uuid_pkg.UUID | None] = mapped_column(ForeignKey("user.id"), index=True, default=None, init=False)
    data: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
