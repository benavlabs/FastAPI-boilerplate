import uuid as uuid_pkg

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from ..core.db.database import Base
from ..core.db.models import SoftDeleteMixin, TimestampMixin, UUIDMixin


class Post(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "post"

    created_by_user_id: Mapped[uuid_pkg.UUID] = mapped_column(ForeignKey("user.id"), index=True)
    title: Mapped[str] = mapped_column(String(30))
    text: Mapped[str] = mapped_column(String(63206))
    media_url: Mapped[str | None] = mapped_column(String, default=None)
