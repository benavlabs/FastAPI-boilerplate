"""Unit tests for the crudauth-backed auth dependencies.

The integration fixtures (`auth_client` / `superuser_auth_client`) override these
functions, so the real bodies — the dict re-load, the soft-delete filter, and the
superuser 403 branch — are only exercised here, called directly with a Principal
and a mocked ``crud_users.get``.
"""

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
            await deps.get_current_user(principal=Principal(user_id=1), db=MagicMock())


@pytest.mark.asyncio
async def test_get_current_user_returns_dict_and_filters_soft_deleted():
    user = {"id": 1, "username": "x", "is_superuser": False}
    mock_get = AsyncMock(return_value=user)
    with patch.object(deps.crud_users, "get", new=mock_get):
        result = await deps.get_current_user(principal=Principal(user_id=1), db=MagicMock())

    assert result == user
    assert mock_get.call_args.kwargs.get("is_deleted") is False


@pytest.mark.asyncio
async def test_get_optional_user_none_principal_returns_none():
    assert await deps.get_optional_user(principal=None, db=MagicMock()) is None


@pytest.mark.asyncio
async def test_get_optional_user_returns_dict():
    user = {"id": 2}
    with patch.object(deps.crud_users, "get", new=AsyncMock(return_value=user)):
        result = await deps.get_optional_user(principal=Principal(user_id=2), db=MagicMock())
    assert result == user


@pytest.mark.asyncio
async def test_get_current_superuser_denies_non_superuser():
    with pytest.raises(ForbiddenException):
        await deps.get_current_superuser(current_user={"id": 1, "is_superuser": False})


@pytest.mark.asyncio
async def test_get_current_superuser_allows_superuser():
    user = {"id": 1, "is_superuser": True}
    assert await deps.get_current_superuser(current_user=user) == user
