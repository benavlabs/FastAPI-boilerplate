"""Unit tests for the user service's authorization rules."""

from typing import Any

import pytest
from crudauth import make_unusable_password
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.common.exceptions import PermissionDeniedError
from src.modules.user.crud import crud_users
from src.modules.user.exceptions import (
    EmailChangeNeedsPasswordError,
    ProviderAccountEmailChangeError,
    UserExistsError,
)
from src.modules.user.schemas import UserCreate, UserUpdate
from src.modules.user.service import UserService

UPDATE = "user.update"


async def _stored(db: AsyncSession, user_id: int) -> dict[str, Any]:
    """The user's row, which each of these tests requires to be there."""
    row = await crud_users.get(db=db, id=user_id)
    assert row is not None

    return row


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


# =============================================================================
# A new address has proved nothing
# =============================================================================
async def test_changing_the_email_drops_the_verification(user_service: UserService, db_session: AsyncSession, test_user: dict):
    """A verified address doesn't vouch for the next one the owner types in."""
    await crud_users.update(db=db_session, object={"email_verified": True}, id=test_user["id"])

    await user_service.update(
        test_user["id"], UserUpdate(email="moved@example.com"), db_session, current_password=test_user["password"]
    )

    moved = await _stored(db_session, test_user["id"])
    assert moved["email"] == "moved@example.com"
    assert moved["email_verified"] is False


async def test_an_update_that_keeps_the_email_keeps_the_verification(
    user_service: UserService, db_session: AsyncSession, test_user: dict
):
    await crud_users.update(db=db_session, object={"email_verified": True}, id=test_user["id"])

    await user_service.update(test_user["id"], UserUpdate(name="Same Address"), db_session)

    unchanged = await _stored(db_session, test_user["id"])
    assert unchanged["email_verified"] is True


async def test_resubmitting_the_same_email_keeps_the_verification(
    user_service: UserService, db_session: AsyncSession, test_user: dict
):
    """A form that posts every field must not cost the user their verification."""
    await crud_users.update(db=db_session, object={"email_verified": True}, id=test_user["id"])

    await user_service.update(test_user["id"], UserUpdate(email=test_user["email"]), db_session)

    unchanged = await _stored(db_session, test_user["id"])
    assert unchanged["email_verified"] is True


# =============================================================================
# One address, whatever case it was typed in
# =============================================================================
async def test_signup_stores_the_address_in_canonical_form(user_service: UserService, db_session: AsyncSession):
    """crudauth looks accounts up in lowercase, so that is what the row has to hold."""
    created = await user_service.create(
        UserCreate(name="Mixed Case", username="mixedcase", email="Alice@Example.COM", password="Str1ngst!"),
        db_session,
    )

    assert created["email"] == "alice@example.com"


async def test_the_same_address_in_another_case_is_still_taken(user_service: UserService, db_session: AsyncSession):
    await user_service.create(
        UserCreate(name="First Owner", username="firstowner", email="owner@example.com", password="Str1ngst!"),
        db_session,
    )

    with pytest.raises(UserExistsError):
        await user_service.create(
            UserCreate(name="Second Owner", username="secondowner", email="OWNER@Example.com", password="Str1ngst!"),
            db_session,
        )


async def test_changing_to_the_same_address_in_another_case_is_refused(
    user_service: UserService, db_session: AsyncSession, test_user: dict
):
    await user_service.create(
        UserCreate(name="Other Person", username="otherperson", email="taken@example.com", password="Str1ngst!"),
        db_session,
    )

    with pytest.raises(UserExistsError):
        await user_service.update(
            test_user["id"], UserUpdate(email="TAKEN@example.com"), db_session, current_password=test_user["password"]
        )


async def test_an_updated_address_is_stored_in_canonical_form(
    user_service: UserService, db_session: AsyncSession, test_user: dict
):
    await user_service.update(
        test_user["id"], UserUpdate(email="Moved@Example.COM"), db_session, current_password=test_user["password"]
    )

    moved = await _stored(db_session, test_user["id"])
    assert moved["email"] == "moved@example.com"


async def test_an_email_change_without_the_password_is_refused(
    user_service: UserService, db_session: AsyncSession, test_user: dict
):
    """The service refuses the change when no requester is given."""
    with pytest.raises(EmailChangeNeedsPasswordError):
        await user_service.update(test_user["id"], UserUpdate(email="moved@example.com"), db_session)

    unchanged = await _stored(db_session, test_user["id"])
    assert unchanged["email"] == test_user["email"]


async def test_an_email_change_by_another_user_needs_no_password(
    user_service: UserService, db_session: AsyncSession, test_user: dict, test_superuser: dict
):
    await user_service.update(test_user["id"], UserUpdate(email="moved@example.com"), db_session, requester=test_superuser)

    moved = await _stored(db_session, test_user["id"])
    assert moved["email"] == "moved@example.com"


async def test_an_account_without_a_usable_password_cannot_move_its_address(
    user_service: UserService, db_session: AsyncSession, test_user: dict
):
    await crud_users.update(db=db_session, object={"hashed_password": make_unusable_password()}, id=test_user["id"])

    with pytest.raises(ProviderAccountEmailChangeError):
        await user_service.update(
            test_user["id"], UserUpdate(email="moved@example.com"), db_session, current_password="anything"
        )


async def test_a_requester_who_is_not_a_superuser_needs_the_password(
    user_service: UserService, db_session: AsyncSession, test_user: dict, test_user_2: dict
):
    with pytest.raises(EmailChangeNeedsPasswordError):
        await user_service.update(test_user["id"], UserUpdate(email="moved@example.com"), db_session, requester=test_user_2)


async def test_a_requester_without_an_id_needs_the_password(
    user_service: UserService, db_session: AsyncSession, test_user: dict
):
    with pytest.raises(EmailChangeNeedsPasswordError):
        await user_service.update(
            test_user["id"], UserUpdate(email="moved@example.com"), db_session, requester={"is_superuser": True}
        )


async def test_a_superuser_changing_their_own_address_needs_the_password(
    user_service: UserService, db_session: AsyncSession, test_superuser: dict
):
    with pytest.raises(EmailChangeNeedsPasswordError):
        await user_service.update(
            test_superuser["id"], UserUpdate(email="moved@example.com"), db_session, requester=test_superuser
        )

    await user_service.update(
        test_superuser["id"],
        UserUpdate(email="moved@example.com"),
        db_session,
        requester=test_superuser,
        current_password=test_superuser["password"],
    )
    moved = await _stored(db_session, test_superuser["id"])
    assert moved["email"] == "moved@example.com"
