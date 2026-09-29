"""What the tiers feature adds to the user model and the user schemas.

Listed in ``wiring.models``, so ``User`` gains ``tier_id`` and ``tier``, and the
read schemas gain ``tier_id``, without the user module knowing tiers exist.
"""

from typing import TYPE_CHECKING

from pydantic import BaseModel
from sqlalchemy import ForeignKey, Integer
from sqlalchemy.orm import Mapped, MappedAsDataclass, declared_attr, mapped_column, relationship

if TYPE_CHECKING:
    from .models import Tier


class UserTierColumns(MappedAsDataclass):
    """``user.tier_id`` and the ``User.tier`` relationship."""

    tier_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("tiers.id"),
        index=True,
        default=None,
        kw_only=True,
    )

    @declared_attr
    def tier(cls) -> Mapped["Tier | None"]:
        return relationship("Tier", back_populates="users", lazy="selectin", init=False)


class UserTierFields(BaseModel):
    """``tier_id`` on the user read schemas."""

    tier_id: int | None = None
