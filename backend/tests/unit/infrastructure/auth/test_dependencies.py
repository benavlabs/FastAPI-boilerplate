"""Unit tests for the crudauth-backed auth dependencies."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from crudauth import Principal
from crudauth.exceptions import ForbiddenException, UnauthorizedException

from src.infrastructure.auth import dependencies as deps


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
    assert await deps.get_optional_user(
        principal=None,
        db=MagicMock(),
    ) is None


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


@pytest.mark.asyncio
async def test_load_permissions_returns_registered_permissions():
    principal = Principal(user_id=1)

    result_mock = MagicMock()
    result_mock.scalars.return_value.all.return_value = [
        "user.read",
        "user.update",
    ]

    session = MagicMock()
    session.execute = AsyncMock(return_value=result_mock)

    session_context = MagicMock()
    session_context.__aenter__ = AsyncMock(return_value=session)
    session_context.__aexit__ = AsyncMock(return_value=None)

    with patch.object(deps, "local_session", return_value=session_context):
        permissions = await deps.load_permissions(principal)

    assert permissions == frozenset({"user.read", "user.update"})
    session.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_load_permissions_superuser_bypasses_database():
    principal = Principal(user_id=1, is_superuser=True)

    with patch.object(deps, "local_session") as local_session:
        permissions = await deps.load_permissions(principal)

    assert permissions == frozenset(deps.all_permissions())
    local_session.assert_not_called()


def _get_permission_check(*permissions: str):
    """Capture the check callback passed to crudauth.current_user()."""
    with patch.object(deps.auth, "current_user") as current_user:
        current_user.return_value = MagicMock()
        deps.require_permissions(*permissions)

        return current_user.call_args.kwargs["check"]


@pytest.mark.asyncio
async def test_require_permissions_allows_principal_with_required_permissions():
    check = _get_permission_check("user.read")

    with patch.object(
        deps,
        "load_permissions",
        new=AsyncMock(return_value=frozenset({"user.read", "user.update"})),
    ):
        allowed = await check(Principal(user_id=1))

    assert allowed is True


@pytest.mark.asyncio
async def test_require_permissions_requires_all_permissions():
    check = _get_permission_check("user.read", "user.update")

    with patch.object(
        deps,
        "load_permissions",
        new=AsyncMock(return_value=frozenset({"user.read"})),
    ):
        allowed = await check(Principal(user_id=1))

    assert allowed is False


@pytest.mark.asyncio
async def test_require_permissions_superuser_bypasses_permission_lookup():
    check = _get_permission_check("user.read")

    with patch.object(
        deps,
        "load_permissions",
        new=AsyncMock(),
    ) as load_permissions:
        allowed = await check(Principal(user_id=1, is_superuser=True))

    assert allowed is True
    load_permissions.assert_not_awaited()


def test_require_permissions_rejects_unknown_permission():
    with pytest.raises(ValueError, match="Unknown permission name"):
        deps.require_permissions("user.reed")