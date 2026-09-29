"""The contributions features make to each other's extension points.

Hand-maintained until the generator exists: imports and literals only.
"""

from ..infrastructure.composition import PermissionSource
from ..modules.role.sources import role_permissions

PERMISSION_SOURCES: tuple[PermissionSource, ...] = (role_permissions,)
