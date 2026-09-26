"""Central registry for module-defined permissions."""

import importlib
import pkgutil
from enum import StrEnum


_registered_permissions: dict[str, type[StrEnum]] = {}


def register_permissions(resource: str):
    """Register the permission enum for a resource."""

    def decorator(enum_class: type[StrEnum]) -> type[StrEnum]:
        if resource in _registered_permissions:
            raise ValueError(
                f"Permissions for resource '{resource}' are already registered."
            )

        expected_prefix = f"{resource}."
        for permission in enum_class:
            if not permission.value.startswith(expected_prefix):
                raise ValueError(
                    f"Permission '{permission.value}' must start with "
                    f"'{expected_prefix}'."
                )

        _registered_permissions[resource] = enum_class
        return enum_class

    return decorator


def all_permissions() -> frozenset[str]:
    """Return every registered permission name."""

    return frozenset(
        permission.value
        for enum_class in _registered_permissions.values()
        for permission in enum_class
    )


def permission_groups() -> dict[str, tuple[str, ...]]:
    """Return permissions grouped by resource."""

    return {
        resource: tuple(permission.value for permission in enum_class)
        for resource, enum_class in _registered_permissions.items()
    }


def is_known_permission(permission_name: str) -> bool:
    """Return whether a permission is registered."""

    return permission_name in all_permissions()


def discover_permissions(package_name: str) -> None:
    """Import every permissions module below the given package."""

    package = importlib.import_module(package_name)

    for _, module_name, _ in pkgutil.walk_packages(
        package.__path__,
        package.__name__ + ".",
    ):
        if module_name.endswith(".permissions"):
            importlib.import_module(module_name)