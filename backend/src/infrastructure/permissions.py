"""Central registry for module-defined permissions.

Each module declares its own permissions as a ``StrEnum`` decorated with
``@register_permissions("<resource>")``. The registry is what validates a stored
permission name and what the admin UI groups by resource. It belongs to no
feature: the authorization checks read it, and any module may declare into it
without depending on whoever grants the permissions.

Reading the registry discovers the declarations first. ``require_permissions``
validates names at import time, when a route is declared, so a route module that
is imported on its own -- by Alembic, a worker or a script -- has to see every
permission without something else having imported ``src.modules`` beforehand.
"""

import importlib
import pkgutil
import re
from enum import StrEnum

PERMISSION_NAME_MAX_LENGTH = 100

PERMISSIONS_PACKAGE = "src.modules"

RESOURCE_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
ACTION_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")

_registered_permissions: dict[str, type[StrEnum]] = {}
_known_permissions: frozenset[str] = frozenset()
_discovered = False


def _validate(resource: str, enum_class: type[StrEnum]) -> None:
    """Reject a registration that the stored permission column can't hold or a check can't match."""
    if not (isinstance(enum_class, type) and issubclass(enum_class, StrEnum)):
        raise TypeError(f"Permissions for resource '{resource}' must be a StrEnum subclass.")

    if resource in _registered_permissions:
        raise ValueError(f"Permissions for resource '{resource}' are already registered.")

    if not RESOURCE_PATTERN.match(resource):
        raise ValueError(f"Resource '{resource}' must match {RESOURCE_PATTERN.pattern}.")

    members = list(enum_class)
    if not members:
        raise ValueError(f"Permissions for resource '{resource}' must define at least one permission.")

    for permission in members:
        value = permission.value
        resource_name, separator, action = value.partition(".")

        if not separator or resource_name != resource:
            raise ValueError(f"Permission '{value}' must start with '{resource}.'.")

        if not ACTION_PATTERN.match(action):
            raise ValueError(f"Permission '{value}' must name one action matching {ACTION_PATTERN.pattern}.")

        if len(value) > PERMISSION_NAME_MAX_LENGTH:
            raise ValueError(f"Permission '{value}' is longer than {PERMISSION_NAME_MAX_LENGTH} characters.")


def register_permissions(resource: str):
    """Register the permission enum for a resource."""

    def decorator(enum_class: type[StrEnum]) -> type[StrEnum]:
        global _known_permissions

        _validate(resource, enum_class)

        _registered_permissions[resource] = enum_class
        _known_permissions |= {permission.value for permission in enum_class}

        return enum_class

    return decorator


def discover_permissions(package_name: str = PERMISSIONS_PACKAGE) -> None:
    """Import every permissions module below the given package, once."""
    global _discovered

    if _discovered:
        return

    _discovered = True
    package = importlib.import_module(package_name)

    for _, module_name, _ in pkgutil.walk_packages(package.__path__, package.__name__ + "."):
        if module_name.endswith(".permissions"):
            importlib.import_module(module_name)


def all_permissions() -> frozenset[str]:
    """Return every registered permission name."""
    discover_permissions()

    return _known_permissions


def permission_groups() -> dict[str, tuple[str, ...]]:
    """Return permissions grouped by resource, for a UI that offers them per resource."""
    discover_permissions()

    return {
        resource: tuple(permission.value for permission in enum_class)
        for resource, enum_class in _registered_permissions.items()
    }


def registered_permissions(names: list[str]) -> list[str]:
    """``names`` with the duplicates dropped, refusing one the registry doesn't know.

    Raises:
        ValueError: A name is not a registered permission, so nothing would ever check it.
    """
    unknown = sorted(set(names) - all_permissions())
    if unknown:
        raise ValueError(f"Unknown permission(s): {', '.join(unknown)}")

    return sorted(set(names))


def is_known_permission(permission_name: str) -> bool:
    """Return whether a permission is registered."""
    discover_permissions()

    return permission_name in _known_permissions
