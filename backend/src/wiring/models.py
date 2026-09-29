"""Extension points of the user model: what other features add to ``User``.

Hand-maintained until the generator exists.
"""

from ..modules.role.contrib import UserRoleColumns


class UserModelExtensions(UserRoleColumns):
    """Columns and relationships other features add to ``User``."""
