"""The model views the admin panel registers.

Hand-maintained until the generator exists.
"""

from ..modules.tier.admin import TierAdmin
from ..modules.user.admin import UserAdmin

ADMIN_VIEWS: tuple[type, ...] = (
    UserAdmin,
    TierAdmin,
)
