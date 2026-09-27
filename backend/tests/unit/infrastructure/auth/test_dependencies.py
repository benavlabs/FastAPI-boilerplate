"""Unit tests for the crudauth-backed auth dependencies.

The auth fixtures in ``tests/conftest.py`` override ``get_current_user`` and
``get_current_principal`` rather than carrying a real session, so a route that
reads the principal or the caller's permissions keeps working under them. Tests
for the permission rules themselves sign in for real; see
``tests/integration/api/v1/users/test_permissions.py``.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from crudauth import Principal
from crudauth.exceptions import ForbiddenException, UnauthorizedException
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.auth import dependencies as deps
from src.modules.role.models import Role, RolePermission, UserRole
from src.modules.role.permission_registry import all_permissions


@pytest.mark.asyncio
async def test_get_current_user_no_principal_raises():
    with pytest.raises(UnauthorizedException):
        await deps.get_current_user(principal=None, db=MagicMock())


@pytest.mark.asyncio
async def test_get_current_user_missing_row_raises():
    """A valid principal whose row is gone/soft-deleted re-loads to None → 401."""
    with patch.object(deps.crud_users, "get", new=AsyncMock(return_value=None)):
        with pytest.raises(UnauthorizedException):
            await deps.get_current_user(
                principal=Principal(user_id=1),
                db=MagicMock(),
            )


@pytest.mark.asyncio
async def test_get_current_user_returns_dict_and_filters_soft_deleted():
    user = {"id": 1, "username": "x", "is_superuser": False}
    mock_get = AsyncMock(return_value=user)

    with patch.object(deps.crud_users, "get", new=mock_get):
        result = await deps.get_current_user(
            principal=Principal(user_id=1),
            db=MagicMock(),
        )

    assert result == user
    assert mock_get.call_args.kwargs.get("is_deleted") is False


@pytest.mark.asyncio
async def test_get_optional_user_none_principal_returns_none():
    assert (
        await deps.get_optional_user(
            principal=None,
            db=MagicMock(),
        )
        is None
    )


@pytest.mark.asyncio
async def test_get_optional_user_returns_dict():
    user = {"id": 2}

    with patch.object(
        deps.crud_users,
        "get",
        new=AsyncMock(return_value=user),
    ):
        result = await deps.get_optional_user(
            principal=Principal(user_id=2),
            db=MagicMock(),
        )

    assert result == user


@pytest.mark.asyncio
async def test_get_current_superuser_denies_non_superuser():
    with pytest.raises(ForbiddenException):
        await deps.get_current_superuser(
            current_user={"id": 1, "is_superuser": False},
        )


@pytest.mark.asyncio
async def test_get_current_superuser_allows_superuser():
    user = {"id": 1, "is_superuser": True}

    assert await deps.get_current_superuser(current_user=user) == user


# =============================================================================
# Permission loading and the require_permissions gate, against a real database
# =============================================================================
async def _role_with(db: AsyncSession, name: str, *permissions: str) -> Role:
    role = Role(name=name)
    db.add(role)
    await db.flush()
    db.add_all([RolePermission(role_id=role.id, permission_name=p) for p in permissions])
    await db.commit()
    return role


async def test_load_permissions_reads_the_roles_assigned_to_the_user(db_session: AsyncSession, test_user: dict):
    role = await _role_with(db_session, "reader", "user.read", "tier.read")
    db_session.add(UserRole(user_id=test_user["id"], role_id=role.id))
    await db_session.commit()

    permissions = await deps.load_permissions(db_session, test_user["id"])

    assert permissions == {"user.read", "tier.read"}


async def test_load_permissions_is_empty_without_a_role(db_session: AsyncSession, test_user: dict):
    assert await deps.load_permissions(db_session, test_user["id"]) == frozenset()


async def test_load_permissions_grants_a_superuser_everything_without_a_query(db_session: AsyncSession):
    permissions = await deps.load_permissions(db_session, 999999, is_superuser=True)

    assert permissions == all_permissions()


async def test_load_permissions_ignores_a_stored_name_that_is_no_longer_registered(db_session: AsyncSession, test_user: dict):
    """A permission removed from the code must not keep granting anything."""
    role = await _role_with(db_session, "stale", "user.read")
    await db_session.execute(
        insert(RolePermission).values(
            role_id=role.id,
            permission_name="user.retired",
            created_at=datetime.now(UTC),
        )
    )
    db_session.add(UserRole(user_id=test_user["id"], role_id=role.id))
    await db_session.commit()

    assert await deps.load_permissions(db_session, test_user["id"]) == {"user.read"}


def test_require_permissions_rejects_unknown_permission():
    with pytest.raises(ValueError, match="Unknown permission name"):
        deps.require_permissions("user.reed")


# =============================================================================
# Escalation helpers
# =============================================================================
async def test_a_principal_can_delegate_what_it_holds(db_session: AsyncSession, test_user: dict):
    role = await _role_with(db_session, "editor", "user.read", "user.update")
    db_session.add(UserRole(user_id=test_user["id"], role_id=role.id))
    await db_session.commit()
    principal = Principal(user_id=test_user["id"])

    assert await deps.can_delegate_permissions(db_session, principal, ["user.read"])
    assert not await deps.can_delegate_permissions(db_session, principal, ["user.read", "user.delete"])


async def test_a_superuser_can_delegate_anything_registered(db_session: AsyncSession):
    principal = Principal(user_id=1, is_superuser=True)

    assert await deps.can_delegate_permissions(db_session, principal, sorted(all_permissions()))


async def test_an_unregistered_permission_is_never_delegable(db_session: AsyncSession):
    """A typo or a removed permission is refused rather than raising into the route."""
    superuser = Principal(user_id=1, is_superuser=True)

    assert not await deps.can_delegate_permissions(db_session, superuser, ["user.reed"])


async def test_assigning_a_role_needs_every_permission_it_carries(db_session: AsyncSession, test_user: dict):
    held = await _role_with(db_session, "held", "user.read")
    stronger = await _role_with(db_session, "stronger", "user.read", "user.delete")
    weaker = await _role_with(db_session, "weaker", "user.read")
    db_session.add(UserRole(user_id=test_user["id"], role_id=held.id))
    await db_session.commit()
    principal = Principal(user_id=test_user["id"])

    assert await deps.can_assign_role(db_session, principal, weaker.id)
    assert not await deps.can_assign_role(db_session, principal, stronger.id)


async def test_a_role_carrying_nothing_is_assignable(db_session: AsyncSession, test_user: dict):
    empty = await _role_with(db_session, "empty")
    principal = Principal(user_id=test_user["id"])

    assert await deps.can_assign_role(db_session, principal, empty.id)


async def test_a_superuser_can_assign_any_role(db_session: AsyncSession):
    strong = await _role_with(db_session, "strong", "user.delete")

    assert await deps.can_assign_role(db_session, Principal(user_id=1, is_superuser=True), strong.id)
