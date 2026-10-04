"""Extension points of the user model: what other features add to ``User``.

Hand-maintained until the generator exists.
"""

from ..modules.role.contrib import UserRoleColumns
from ..modules.tier.contrib import UserTierColumns, UserTierFields


class UserModelExtensions(UserRoleColumns, UserTierColumns):
    """Columns and relationships other features add to ``User``."""


class UserSchemaExtensions(UserTierFields):
    """Fields other features add to the user read schemas."""
