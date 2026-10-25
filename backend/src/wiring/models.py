"""Extension points of the user model: what other features add to ``User``.

Written by the generator in `tools/removal_drill.py`, which a test compares this file against.
"""

from ..modules.role.contrib import UserRoleColumns
from ..modules.tier.contrib import UserTierColumns, UserTierFields


class UserModelExtensions(UserRoleColumns, UserTierColumns):
    """Columns and relationships other features add to ``User``."""


class UserSchemaExtensions(UserTierFields):
    """Fields other features add to the user read schemas."""
