"""The registry is what validates a stored permission name, so it has to be strict."""

import subprocess
import sys
from enum import StrEnum
from pathlib import Path

import pytest

from src.infrastructure.permissions import (
    PERMISSION_NAME_MAX_LENGTH,
    all_permissions,
    permission_groups,
    register_permissions,
)


def test_registered_permissions_are_flat_and_grouped():
    """Whatever a project registers, the flat set and the groups describe the same names."""
    permissions = all_permissions()
    groups = permission_groups()

    assert permissions == {name for names in groups.values() for name in names}
    for resource, names in groups.items():
        assert all(name.startswith(f"{resource}.") for name in names)


def test_register_permissions_rejects_wrong_resource_prefix():
    class InvalidPermission(StrEnum):
        READ = "other.read"

    with pytest.raises(ValueError, match="must start with 'test_resource.'"):
        register_permissions("test_resource")(InvalidPermission)


def test_register_permissions_rejects_duplicate_resource():
    class FirstPermission(StrEnum):
        READ = "duplicated.read"

    class SecondPermission(StrEnum):
        WRITE = "duplicated.write"

    register_permissions("duplicated")(FirstPermission)

    with pytest.raises(
        ValueError,
        match="Permissions for resource 'duplicated' are already registered",
    ):
        register_permissions("duplicated")(SecondPermission)


def test_register_permissions_rejects_a_nested_name():
    """Permissions are flat ``resource.action``; a deeper name has no meaning here."""

    class NestedPermission(StrEnum):
        READ = "billing.invoice.read"

    with pytest.raises(ValueError, match="one action"):
        register_permissions("billing")(NestedPermission)


def test_register_permissions_rejects_a_dotted_resource():
    class DottedPermission(StrEnum):
        READ = "billing.invoice.read"

    with pytest.raises(ValueError, match="must match"):
        register_permissions("billing.invoice")(DottedPermission)


def test_register_permissions_rejects_an_empty_action():
    class EmptyActionPermission(StrEnum):
        READ = "empty."

    with pytest.raises(ValueError, match="one action"):
        register_permissions("empty")(EmptyActionPermission)


def test_register_permissions_rejects_a_name_the_column_cannot_hold():
    action = "a" * PERMISSION_NAME_MAX_LENGTH

    class LongPermission(StrEnum):
        READ = f"long.{action}"

    with pytest.raises(ValueError, match="longer than"):
        register_permissions("long")(LongPermission)


def test_register_permissions_rejects_uppercase_and_spaces():
    class WeirdPermission(StrEnum):
        READ = "weird.Do Thing"

    with pytest.raises(ValueError, match="one action"):
        register_permissions("weird")(WeirdPermission)


def test_register_permissions_rejects_an_empty_enum():
    class NoPermission(StrEnum):
        pass

    with pytest.raises(ValueError, match="at least one permission"):
        register_permissions("blank")(NoPermission)


def test_register_permissions_rejects_a_class_that_is_not_a_str_enum():
    class NotAnEnum:
        READ = "plain.read"

    with pytest.raises(TypeError, match="StrEnum"):
        register_permissions("plain")(NotAnEnum)


def test_no_resource_can_claim_a_name_another_resource_owns():
    """The prefix rule is what keeps one permission name owned by one resource."""

    class ShadowPermission(StrEnum):
        READ = "user.read"
        OWN = "shadow.own"

    with pytest.raises(ValueError, match="must start with 'shadow.'"):
        register_permissions("shadow")(ShadowPermission)


def test_a_failed_registration_leaves_the_registry_untouched():
    before = all_permissions()

    class BadPermission(StrEnum):
        READ = "other.read"

    with pytest.raises(ValueError):
        register_permissions("leftover")(BadPermission)

    assert all_permissions() == before
    assert "leftover" not in permission_groups()


def test_reading_the_registry_discovers_the_declarations():
    """Nothing imports the permission modules on the app's behalf any more.

    A process that only reads the registry has to end up with the declarations,
    because that is what makes ``require_permissions`` valid at import time in a
    module imported on its own.
    """
    result = _in_a_cold_process(
        "from pathlib import Path\n"
        "from src.infrastructure.permissions import all_permissions\n"
        "declared = list(Path('src/modules').glob('*/permissions.py'))\n"
        "assert all_permissions() or not declared, 'reading the registry discovered nothing'\n"
    )

    assert result.returncode == 0, result.stderr


def _in_a_cold_process(code: str) -> subprocess.CompletedProcess[str]:
    """Run ``code`` in a process that has imported nothing of the app yet."""
    backend = Path(__file__).resolve().parents[3]

    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=backend,
        capture_output=True,
        text=True,
        env={
            "PATH": "/usr/bin:/bin",
            "PYTHONPATH": str(backend),
            "SECRET_KEY": "test_secret_key_for_tests",
            "SESSION_BACKEND": "memory",
            "RATE_LIMITER_BACKEND": "memory",
        },
    )
