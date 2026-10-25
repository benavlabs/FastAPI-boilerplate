"""Unit tests for the user service's authorization rules."""

from typing import Any

import pytest
from fastapi import BackgroundTasks
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

import src.modules.user.service as service_module
from src.modules.common.exceptions import PermissionDeniedError
from src.modules.user.crud import crud_users
from src.modules.user.exceptions import (
    EmailAlreadyRegisteredError,
    UserExistsError,
)
from src.modules.user.routes import SIGNUP_ACCEPTED, create_user
from src.modules.user.schemas import UserAdminUpdate, UserCreate, UserUpdate
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
    await user_service.verify_update_permission(_user("alice"), "alice", frozenset(), is_superuser=False, scoped=False)


async def test_a_user_cannot_update_another_profile_without_the_permission(user_service: UserService):
    with pytest.raises(PermissionDeniedError):
        await user_service.verify_update_permission(_user("alice"), "bob", frozenset(), is_superuser=False, scoped=False)


async def test_the_update_permission_allows_editing_another_profile(user_service: UserService):
    await user_service.verify_update_permission(_user("alice"), "bob", frozenset({UPDATE}), is_superuser=False, scoped=False)


async def test_a_superuser_can_update_another_profile(user_service: UserService):
    await user_service.verify_update_permission(
        _user("alice", is_superuser=True), "bob", frozenset(), is_superuser=True, scoped=False
    )


async def test_a_superusers_scoped_credential_cannot_update_another_profile(user_service: UserService):
    """The acting credential decides, not the row: a key carries no superuser flag."""
    with pytest.raises(PermissionDeniedError):
        await user_service.verify_update_permission(
            _user("alice", is_superuser=True), "bob", frozenset(), is_superuser=False, scoped=True
        )


async def test_a_scoped_credential_cannot_update_its_own_profile_without_the_permission(user_service: UserService):
    """A key scoped to nothing carries its owner's ownership and none of its permissions."""
    with pytest.raises(PermissionDeniedError):
        await user_service.verify_update_permission(_user("alice"), "alice", frozenset(), is_superuser=False, scoped=True)


async def test_a_scoped_credential_with_the_permission_can_update_its_own_profile(user_service: UserService):
    await user_service.verify_update_permission(_user("alice"), "alice", frozenset({UPDATE}), is_superuser=False, scoped=True)


async def test_the_update_permission_does_not_grant_the_other_actions(user_service: UserService):
    """``user.update`` is about updating; deleting another account stays owner-or-superuser."""
    with pytest.raises(PermissionDeniedError):
        await user_service.verify_user_permission(_user("alice"), "bob", "delete this account", is_superuser=False)


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
# Which credential was taken decides how a signup answers
# =============================================================================
async def test_an_address_that_already_has_an_account_is_its_own_error(user_service: UserService, db_session: AsyncSession):
    """The route answers it the way it answers a signup that worked, so it has to be told apart."""
    await user_service.create(
        UserCreate(name="Owner", username="theowner", email="owner@example.com", password="Str1ngst!"), db_session
    )

    with pytest.raises(EmailAlreadyRegisteredError):
        await user_service.create(
            UserCreate(name="Stranger", username="astranger", email="owner@example.com", password="Str1ngst!"),
            db_session,
        )


async def test_a_taken_username_stays_a_conflict(user_service: UserService, db_session: AsyncSession):
    """A username is public, so a signup form is told, and the error is the plain one."""
    await user_service.create(
        UserCreate(name="Owner", username="takenname", email="first@example.com", password="Str1ngst!"), db_session
    )

    with pytest.raises(UserExistsError) as refused:
        await user_service.create(
            UserCreate(name="Stranger", username="takenname", email="second@example.com", password="Str1ngst!"),
            db_session,
        )

    assert not isinstance(refused.value, EmailAlreadyRegisteredError)


async def test_a_signup_for_a_taken_address_still_pays_for_the_hash(
    user_service: UserService, db_session: AsyncSession, test_user: dict, monkeypatch
):
    """Hashing only where the address was free tells a caller by the clock what the answer won't.

    bcrypt is the slowest thing a signup does, so it runs before either credential is
    looked up.
    """
    hashed: list[str] = []
    real_hash = service_module.get_password_hash_async

    async def recording(password: str) -> str:
        hashed.append(password)

        return await real_hash(password)

    monkeypatch.setattr(service_module, "get_password_hash_async", recording)

    with pytest.raises(EmailAlreadyRegisteredError):
        await user_service.create(
            UserCreate(name="Stranger", username="astranger", email=test_user["email"], password="Str1ngst!"),
            db_session,
        )

    assert hashed == ["Str1ngst!"]


async def test_the_notice_to_an_existing_owner_runs_after_the_answer(
    user_service: UserService, db_session: AsyncSession, test_user: dict, monkeypatch
):
    """Waiting for a mail server on this path alone would give the answer away by the clock.

    Without the taskiq feature the notice goes out over SMTP in the request, so the route
    leaves it to run once the answer is on its way, which is what Starlette does with a
    background task.
    """
    told: list[str] = []

    async def noting(email: str) -> None:
        told.append(email)

    monkeypatch.setattr(user_service, "notify_the_address_owner", noting)
    background = BackgroundTasks()

    answered = await create_user(
        user=UserCreate(name="Stranger", username="astranger", email=test_user["email"], password="Str1ngst!"),
        db=db_session,
        user_service=user_service,
        background=background,
    )

    assert answered == {"message": SIGNUP_ACCEPTED}
    assert told == []
    await background()
    assert told == [test_user["email"]]


async def test_the_index_is_read_from_the_driver_rather_than_the_message(user_service: UserService, db_session: AsyncSession):
    """How a refusal is worded is the driver's to change; the name it puts on the error is not."""

    class _Refusal(Exception):
        constraint_name = "ix_user_email_lower"

    wrapped = Exception("duplicate key value violates a unique index")
    wrapped.__cause__ = _Refusal()

    with pytest.raises(EmailAlreadyRegisteredError):
        await user_service._refuse_taken_credentials(db_session, IntegrityError("INSERT INTO user", {}, wrapped))


@pytest.mark.parametrize(
    ("index", "expected"),
    [
        ("ix_user_email", EmailAlreadyRegisteredError),
        ("ix_user_email_lower", EmailAlreadyRegisteredError),
        ("ix_user_username", UserExistsError),
        ("ix_user_email_of_some_later_table", UserExistsError),
    ],
)
async def test_a_race_is_named_by_the_index_that_refused_the_row(
    user_service: UserService, db_session: AsyncSession, index: str, expected: type[Exception]
):
    """Both pre-checks passed and the database refused the insert, which names what it refused."""
    collision = IntegrityError("INSERT INTO user", {}, Exception(f'duplicate key value violates unique constraint "{index}"'))

    with pytest.raises(expected) as refused:
        await user_service._refuse_taken_credentials(db_session, collision)

    assert isinstance(refused.value, expected)
    if expected is UserExistsError:
        assert not isinstance(refused.value, EmailAlreadyRegisteredError)


# =============================================================================
# A new address has proved nothing
# =============================================================================
async def test_changing_the_email_drops_the_verification(user_service: UserService, db_session: AsyncSession, test_user: dict):
    """A verified address doesn't vouch for the next one the owner types in."""
    await crud_users.update(db=db_session, object={"email_verified": True}, id=test_user["id"])

    await user_service.update(test_user["id"], UserAdminUpdate(email="moved@example.com"), db_session)

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

    await user_service.update(test_user["id"], UserAdminUpdate(email=test_user["email"]), db_session)

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
        await user_service.update(test_user["id"], UserAdminUpdate(email="TAKEN@example.com"), db_session)


async def test_an_updated_address_is_stored_in_canonical_form(
    user_service: UserService, db_session: AsyncSession, test_user: dict
):
    """An administrator's update goes through the same canonicalisation as a signup."""
    await user_service.update(test_user["id"], UserAdminUpdate(email="Moved@Example.COM"), db_session)

    moved = await _stored(db_session, test_user["id"])
    assert moved["email"] == "moved@example.com"
