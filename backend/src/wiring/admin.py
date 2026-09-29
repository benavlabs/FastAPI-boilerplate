"""The model views the admin panel registers.

Hand-maintained until the generator exists.
"""

from ..interfaces.admin.views.tiers import TierAdmin
from ..interfaces.admin.views.users import UserAdmin

ADMIN_VIEWS: tuple[type, ...] = (
    UserAdmin,
    TierAdmin,
)
