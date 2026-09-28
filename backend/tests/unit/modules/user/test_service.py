"""Unit tests for the user service's authorization rules."""

import pytest

from src.modules.common.exceptions import PermissionDeniedError
from src.modules.user.schemas import UserCreate, UserUpdate
from src.modules.user.service import UserService

UPDATE = "user.update"


@pytest.fixture
def user_service() -> UserService:
    """Return a user service instance."""
    return UserService()


def _user(username: str, *, is_superuser: bool = False, email: str = "target@example.com") -> dict:
    return {"id": 1, "username": username, "email": email, "is_superuser": is_superuser}


# =============================================================================
# Who may update a profile at all
# =============================================================================
async def test_a_user_can_update_their_own_profile_without_the_permission(user_service: UserService):
    await user_service.verify_update_permission(_user("alice"), "alice", frozenset())


async def test_a_user_cannot_update_another_profile_without_the_permission(user_service: UserService):
    with pytest.raises(PermissionDeniedError):
        await user_service.verify_update_permission(_user("alice"), "bob", frozenset())


async def test_the_update_permission_allows_editing_another_profile(user_service: UserService):
    await user_service.verify_update_permission(_user("alice"), "bob", frozenset({UPDATE}))


async def test_a_superuser_can_update_another_profile(user_service: UserService):
    await user_service.verify_update_permission(_user("alice", is_superuser=True), "bob", frozenset())


async def test_the_update_permission_does_not_grant_the_other_actions(user_service: UserService):
    """``user.update`` is about updating; deleting another account stays owner-or-superuser."""
    with pytest.raises(PermissionDeniedError):
        await user_service.verify_user_permission(_user("alice"), "bob", "delete this account")


# =============================================================================
# What a user.update holder may do to someone else
# =============================================================================
def test_a_holder_cannot_edit_a_superuser(user_service: UserService):
    with pytest.raises(PermissionDeniedError):
        user_service.verify_no_privilege_escalation(
            _user("bob", is_superuser=True),
            UserUpdate(name="Pwned Name"),
            frozenset({UPDATE}),
            frozenset(),
        )


def test_a_holder_cannot_edit_someone_holding_more(user_service: UserService):
    with pytest.raises(PermissionDeniedError):
        user_service.verify_no_privilege_escalation(
            _user("bob"),
            UserUpdate(name="Pwned Name"),
            frozenset({UPDATE}),
            frozenset({UPDATE, "user.delete"}),
        )


def test_a_holder_can_edit_someone_weaker(user_service: UserService):
    user_service.verify_no_privilege_escalation(
        _user("bob"),
        UserUpdate(name="New Name"),
        frozenset({UPDATE, "user.delete"}),
        frozenset({UPDATE}),
    )


def test_a_holder_cannot_change_another_users_email(user_service: UserService):
    """A verified provider email resolves a login to an account, so this is a takeover."""
    with pytest.raises(PermissionDeniedError, match="email"):
        user_service.verify_no_privilege_escalation(
            _user("bob"),
            UserUpdate(email="attacker@example.com"),
            frozenset({UPDATE}),
            frozenset(),
        )


def test_submitting_the_email_a_user_already_has_is_not_a_change(user_service: UserService):
    user_service.verify_no_privilege_escalation(
        _user("bob", email="bob@example.com"),
        UserUpdate(email="bob@example.com", name="New Name"),
        frozenset({UPDATE}),
        frozenset(),
    )


# =============================================================================
# What signup is allowed to write
# =============================================================================
class SignupWithServerFields(UserCreate):
    """A signup payload that carries columns only the server may set."""

    model_config = {"extra": "allow"}

    email_verified: bool = True
    google_id: str | None = "smuggled-google-sub"
    oauth_provider: str | None = "google"


async def test_signup_cannot_write_the_verification_or_oauth_columns(user_service: UserService, db_session):
    """The public schema refuses these fields; creating the row must not trust them either."""
    created = await user_service.create(
        SignupWithServerFields(
            name="Smuggler",
            username="smuggler",
            email="smuggler@example.com",
            password="Password123!",
        ),
        db_session,
    )

    assert created["email_verified"] is False
    assert created["oauth_provider"] is None
