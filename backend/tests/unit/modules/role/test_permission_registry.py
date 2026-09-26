import pytest
from enum import StrEnum

from src.modules.role.permission_registry import (
    all_permissions,
    permission_groups,
    register_permissions,
)


def test_registered_permissions_are_flat_and_grouped():
    permissions = all_permissions()
    groups = permission_groups()

    assert permissions
    assert permissions == {
        permission
        for group in groups.values()
        for permission in group
    }

    assert "user.read" in permissions
    assert "role.assign" in permissions
    assert "tier.update" in permissions

    assert groups["user"] == (
        "user.read",
        "user.create",
        "user.update",
        "user.delete",
    )


def test_register_permissions_rejects_wrong_resource_prefix():
    class InvalidPermission(StrEnum):
        READ = "other.read"

    with pytest.raises(ValueError, match="must start with 'test_resource.'"):
        register_permissions("test_resource")(InvalidPermission)


def test_register_permissions_rejects_duplicate_resource():
    class DuplicatePermission(StrEnum):
        READ = "user.read"

    with pytest.raises(
        ValueError,
        match="Permissions for resource 'user' are already registered",
    ):
        register_permissions("user")(DuplicatePermission)