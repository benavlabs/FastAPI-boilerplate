import uuid as uuid_pkg

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from ..core.db.database import Base
from ..core.db.models import SoftDeleteMixin, TimestampMixin, UUIDMixin


class User(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "user"

    name: Mapped[str] = mapped_column(String(30))
    username: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String)

    profile_image_url: Mapped[str] = mapped_column(String, default="https://profileimageurl.com")
    is_superuser: Mapped[bool] = mapped_column(default=False)

    tier_id: Mapped[uuid_pkg.UUID | None] = mapped_column(ForeignKey("tier.uuid"), index=True, default=None, init=False)
