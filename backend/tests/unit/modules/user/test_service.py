"""Unit tests for user service authorization."""

import pytest

from src.modules.common.exceptions import PermissionDeniedError
from src.modules.user.service import UserService


@pytest.fixture
def user_service() -> UserService:
    """Return a user service instance."""
    return UserService()


@pytest.mark.asyncio
async def test_user_can_update_own_profile_without_update_permission(
    user_service: UserService,
):
    """A user can update their own profile without user.update."""
    requester = {
        "username": "alice",
        "is_superuser": False,
    }

    await user_service.verify_user_permission(
        requester,
        "alice",
        "update profile",
        permissions=frozenset(),
    )


@pytest.mark.asyncio
async def test_user_cannot_update_another_profile_without_update_permission(
    user_service: UserService,
):
    """A user without user.update cannot update another user's profile."""
    requester = {
        "username": "alice",
        "is_superuser": False,
    }

    with pytest.raises(PermissionDeniedError):
        await user_service.verify_user_permission(
            requester,
            "bob",
            "update profile",
            permissions=frozenset(),
        )


@pytest.mark.asyncio
async def test_user_with_update_permission_can_update_another_profile(
    user_service: UserService,
):
    """The user.update permission allows updating another user's profile."""
    requester = {
        "username": "alice",
        "is_superuser": False,
    }

    await user_service.verify_user_permission(
        requester,
        "bob",
        "update profile",
        permissions=frozenset({"user.update"}),
    )


@pytest.mark.asyncio
async def test_superuser_can_update_another_profile(
    user_service: UserService,
):
    """A superuser can update another user's profile."""
    requester = {
        "username": "alice",
        "is_superuser": True,
    }

    await user_service.verify_user_permission(
        requester,
        "bob",
        "update profile",
        permissions=frozenset(),
    )