"""The recovery flows crudauth mounts: verification, password reset, email change.

crudauth owns the tokens and the rules; these drive the mounted routes with a sender
that keeps what it was asked to deliver, and hold the behaviour this project relies on.
"""

import logging
from typing import Any

import pytest
import pytest_asyncio
from crudauth import EmailContext, EmailSender, make_unusable_password
from crudauth.email.constants import EmailKind
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.auth.deps import REDIRECT_MAX_LENGTH
from src.infrastructure.auth.setup import email_config
from src.infrastructure.config.settings import settings
from src.interfaces.main import app
from src.modules.common.constants import INVALID_REQUEST_MESSAGE
from src.modules.user.models import User
from tests.fixtures.accounts import reset_recovery_budgets

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("fresh_login_lockout")]

NEW_PASSWORD = "An0therPassword!"
WRONG_PASSWORD = "NotTheOne123!"
UNKNOWN_ADDRESS = "nobody@example.com"
MOVED_ADDRESS = "moved@example.com"
VERIFY_SENT = "If an account exists, a verification email has been sent."
RESET_SENT = "If an account exists, a password reset email has been sent."


class _CapturingSender(EmailSender):
    """Keeps every message instead of delivering it."""

    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []

    async def send(self, *, to: str, subject: str, body: str, kind: EmailKind, context: EmailContext) -> None:
        self.sent.append({"to": to, "subject": subject, "body": body, "kind": kind, "link": context.link})


@pytest_asyncio.fixture(autouse=True)
async def fresh_recovery_budget(test_user: dict):
    """Clear what the flows count per address and per client address before each test."""
    await reset_recovery_budgets(test_user["email"], UNKNOWN_ADDRESS, MOVED_ADDRESS)


@pytest.fixture
def delivered(monkeypatch) -> list[dict[str, Any]]:
    """What the flows asked to have delivered, in order."""
    capturing = _CapturingSender()
    monkeypatch.setattr(email_config, "sender", capturing)

    return capturing.sent


def _token_of(message: dict[str, Any]) -> str:
    """The signed token out of the link the message carries."""
    link = str(message["link"])
    assert link.startswith(f"{settings.FRONTEND_URL.rstrip('/')}/"), link

    return link.split("token=")[1]


async def _login(client: AsyncClient, user: dict, password: str | None = None) -> str:
    response = await client.post(
        "/api/v1/auth/login",
        data={"username": user["username"], "password": password or user["password"]},
    )
    assert response.status_code == 200, response.text
    token: str = response.json()["csrf_token"]

    return token


async def _second_session(user: dict) -> AsyncClient:
    client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    await _login(client, user)

    return client


async def _soft_delete(db_session: AsyncSession, user: dict) -> None:
    stored = await db_session.get(User, user["id"])
    assert stored is not None
    stored.is_deleted = True
    await db_session.commit()


class TestVerifyingAnAddress:
    """The link the verification request sends marks the address verified, once."""

    async def test_the_link_verifies_the_address(
        self, client: AsyncClient, test_user: dict, delivered: list[dict[str, Any]], db_session: AsyncSession
    ):
        requested = await client.post("/api/v1/auth/email/verify-request", json={"email": test_user["email"]})

        assert requested.status_code == 200
        assert requested.json() == {"detail": VERIFY_SENT}
        assert [(message["to"], message["kind"]) for message in delivered] == [(test_user["email"], "verify_email")]

        confirmed = await client.post("/api/v1/auth/email/verify-confirm", json={"token": _token_of(delivered[0])})

        assert confirmed.status_code == 200
        stored = await db_session.get(User, test_user["id"])
        assert stored is not None
        await db_session.refresh(stored)
        assert stored.email_verified is True

    async def test_the_link_is_refused_the_second_time(
        self, client: AsyncClient, test_user: dict, delivered: list[dict[str, Any]]
    ):
        await client.post("/api/v1/auth/email/verify-request", json={"email": test_user["email"]})
        token = _token_of(delivered[0])
        assert (await client.post("/api/v1/auth/email/verify-confirm", json={"token": token})).status_code == 200

        reused = await client.post("/api/v1/auth/email/verify-confirm", json={"token": token})

        assert reused.status_code == 400


class TestResettingAPassword:
    """The reset replaces the password and ends every session the account had."""

    async def test_the_link_sets_a_new_password_and_ends_every_session(
        self, client: AsyncClient, test_user: dict, delivered: list[dict[str, Any]]
    ):
        other = await _second_session(test_user)
        await _login(client, test_user)
        assert (await other.get("/api/v1/users/me")).status_code == 200

        await client.post("/api/v1/auth/password/reset-request", json={"email": test_user["email"]})
        reset = await client.post(
            "/api/v1/auth/password/reset-confirm",
            json={"token": _token_of(delivered[0]), "new_password": NEW_PASSWORD},
        )

        assert reset.status_code == 200
        assert [(message["to"], message["kind"]) for message in delivered] == [(test_user["email"], "reset_password")]
        assert (await other.get("/api/v1/users/me")).status_code == 401
        assert (await client.get("/api/v1/users/me")).status_code == 401

        client.cookies.clear()
        with_the_old = await client.post(
            "/api/v1/auth/login", data={"username": test_user["username"], "password": test_user["password"]}
        )

        assert with_the_old.status_code == 401
        await _login(client, test_user, NEW_PASSWORD)
        await other.aclose()


class TestAnAccountWithNoPassword:
    """A provider-only account has no password to change, so the reset link sets its first."""

    async def test_the_reset_link_sets_a_first_password(
        self, client: AsyncClient, test_user: dict, delivered: list[dict[str, Any]], db_session: AsyncSession
    ):
        stored = await db_session.get(User, test_user["id"])
        assert stored is not None
        stored.hashed_password = make_unusable_password()
        await db_session.commit()

        refused = await client.post(
            "/api/v1/auth/login", data={"username": test_user["username"], "password": test_user["password"]}
        )
        assert refused.status_code == 401

        await client.post("/api/v1/auth/password/reset-request", json={"email": test_user["email"]})
        reset = await client.post(
            "/api/v1/auth/password/reset-confirm",
            json={"token": _token_of(delivered[0]), "new_password": NEW_PASSWORD},
        )

        assert reset.status_code == 200
        await _login(client, test_user, NEW_PASSWORD)


class TestChangingAnAddress:
    """The new address confirms the change, and the old one is told about it."""

    async def test_confirming_the_change_ends_every_session_the_account_had(
        self, client: AsyncClient, test_user: dict, delivered: list[dict[str, Any]]
    ):
        """The address is what recovers an account, so changing it is a credential change.

        The confirmation is a link clicked from the new mailbox and carries no session, so
        there is none to keep: every session goes and the owner signs in again, as their new
        address. A session somebody else was holding is what this ends.
        """
        other = await _second_session(test_user)
        csrf = await _login(client, test_user)
        assert (await other.get("/api/v1/users/me")).status_code == 200

        await client.post(
            "/api/v1/auth/email/change-request",
            json={"new_email": MOVED_ADDRESS, "password": test_user["password"]},
            headers={"X-CSRF-Token": csrf},
        )
        confirmed = await client.post("/api/v1/auth/email/change-confirm", json={"token": _token_of(delivered[0])})

        assert confirmed.status_code == 200
        assert (await other.get("/api/v1/users/me")).status_code == 401
        assert (await client.get("/api/v1/users/me")).status_code == 401
        await other.aclose()

    async def test_the_old_address_is_notified_once_the_new_one_confirms(
        self, client: AsyncClient, test_user: dict, delivered: list[dict[str, Any]], db_session: AsyncSession
    ):
        csrf = await _login(client, test_user)
        moved = MOVED_ADDRESS

        requested = await client.post(
            "/api/v1/auth/email/change-request",
            json={"new_email": moved, "password": test_user["password"]},
            headers={"X-CSRF-Token": csrf},
        )

        assert requested.status_code == 200
        assert [(message["to"], message["kind"]) for message in delivered] == [(moved, "change_email")]

        confirmed = await client.post("/api/v1/auth/email/change-confirm", json={"token": _token_of(delivered[0])})

        assert confirmed.status_code == 200
        assert [(message["to"], message["kind"]) for message in delivered] == [
            (moved, "change_email"),
            (test_user["email"], "email_changed"),
        ]
        stored = await db_session.get(User, test_user["id"])
        assert stored is not None
        await db_session.refresh(stored)
        assert stored.email == moved


class TestTheBudgetBehindTheAddressChange:
    """The password a change-request checks is counted against the account, not only the address.

    crudauth caps the route per client address; the account's own change-password budget is
    what a caller rotating addresses, or holding a session from one, runs into.
    """

    async def _change_request(self, client: AsyncClient, csrf: str, password: str) -> int:
        response = await client.post(
            "/api/v1/auth/email/change-request",
            json={"new_email": MOVED_ADDRESS, "password": password},
            headers={"X-CSRF-Token": csrf},
        )

        return response.status_code

    async def _change_password(self, client: AsyncClient, csrf: str, password: str) -> int:
        response = await client.post(
            "/api/v1/auth/change-password",
            json={"current_password": password, "new_password": NEW_PASSWORD},
            headers={"X-CSRF-Token": csrf},
        )

        return response.status_code

    async def test_a_wrong_password_here_spends_the_accounts_password_budget(self, client: AsyncClient, test_user: dict):
        """Three guesses here and the account has two left, wherever the next one comes from."""
        csrf = await _login(client, test_user)
        guessed = [await self._change_request(client, csrf, WRONG_PASSWORD) for _ in range(3)]

        left = [await self._change_password(client, csrf, WRONG_PASSWORD) for _ in range(3)]

        assert guessed == [400, 400, 400]
        assert left == [401, 401, 429]

    async def test_a_budget_spent_elsewhere_refuses_the_change(
        self, client: AsyncClient, test_user: dict, delivered: list[dict[str, Any]]
    ):
        csrf = await _login(client, test_user)
        spent = [await self._change_password(client, csrf, WRONG_PASSWORD) for _ in range(5)]

        requested = await self._change_request(client, csrf, test_user["password"])

        assert spent == [401, 401, 401, 401, 401]
        assert requested == 429
        assert delivered == []


class TestADestinationTheLinkWouldCarry:
    """``redirect_to`` is signed into the token, so the link in the mailbox holds it too."""

    @pytest.mark.parametrize(
        "path",
        ["/api/v1/auth/email/verify-request", "/api/v1/auth/password/reset-request"],
    )
    async def test_one_no_link_could_hold_is_refused_and_nothing_is_sent(
        self, client: AsyncClient, test_user: dict, delivered: list[dict[str, Any]], path: str
    ):
        asked = {"email": test_user["email"], "redirect_to": "/" + "a" * REDIRECT_MAX_LENGTH}

        refused = await client.post(path, json=asked)

        assert refused.status_code == 422
        assert delivered == []

    async def test_one_a_link_can_hold_is_sent_and_comes_back_on_the_confirm(
        self, client: AsyncClient, test_user: dict, delivered: list[dict[str, Any]]
    ):
        asked = {"email": test_user["email"], "redirect_to": "/" + "a" * (REDIRECT_MAX_LENGTH - 1)}

        requested = await client.post("/api/v1/auth/email/verify-request", json=asked)
        confirmed = await client.post("/api/v1/auth/email/verify-confirm", json={"token": _token_of(delivered[0])})

        assert requested.status_code == 200
        assert confirmed.json()["redirect_to"] == asked["redirect_to"]


class TestAnAddressWithNoAccount:
    """A request answers the same whether or not the address is in the database."""

    @pytest.mark.parametrize(
        ("path", "detail"),
        [("/api/v1/auth/email/verify-request", VERIFY_SENT), ("/api/v1/auth/password/reset-request", RESET_SENT)],
    )
    async def test_nothing_is_sent_and_the_answer_is_the_same(
        self, client: AsyncClient, test_user: dict, delivered: list[dict[str, Any]], path: str, detail: str
    ):
        known = await client.post(path, json={"email": test_user["email"]})
        delivered.clear()

        unknown = await client.post(path, json={"email": UNKNOWN_ADDRESS})

        assert (unknown.status_code, unknown.json()) == (known.status_code, known.json())
        assert unknown.json() == {"detail": detail}
        assert delivered == []


class TestASoftDeletedAccount:
    """``is_active`` is ``not is_deleted``, and crudauth sends an inactive account nothing."""

    @pytest.mark.parametrize(
        ("path", "detail"),
        [("/api/v1/auth/email/verify-request", VERIFY_SENT), ("/api/v1/auth/password/reset-request", RESET_SENT)],
    )
    async def test_a_request_sends_nothing_and_answers_like_an_unknown_address(
        self,
        client: AsyncClient,
        test_user: dict,
        delivered: list[dict[str, Any]],
        db_session: AsyncSession,
        path: str,
        detail: str,
    ):
        await _soft_delete(db_session, test_user)

        requested = await client.post(path, json={"email": test_user["email"]})
        unknown = await client.post(path, json={"email": UNKNOWN_ADDRESS})

        assert (requested.status_code, requested.json()) == (unknown.status_code, unknown.json())
        assert requested.json() == {"detail": detail}
        assert delivered == []

    async def test_a_reset_link_minted_before_the_delete_is_refused(
        self, client: AsyncClient, test_user: dict, delivered: list[dict[str, Any]], db_session: AsyncSession
    ):
        await client.post("/api/v1/auth/password/reset-request", json={"email": test_user["email"]})
        token = _token_of(delivered[0])
        before = await db_session.get(User, test_user["id"])
        assert before is not None
        hashed_password = before.hashed_password
        await _soft_delete(db_session, test_user)

        refused = await client.post("/api/v1/auth/password/reset-confirm", json={"token": token, "new_password": NEW_PASSWORD})

        assert refused.status_code == 400
        stored = await db_session.get(User, test_user["id"])
        assert stored is not None
        await db_session.refresh(stored)
        assert stored.hashed_password == hashed_password


class TestTextTheDatabaseCannotStore:
    """A lone surrogate in a token reaches ``jwt.decode``, which encodes it and raises."""

    @pytest.mark.parametrize(
        "path",
        [
            "/api/v1/auth/email/verify-confirm",
            "/api/v1/auth/email/change-confirm",
            "/api/v1/auth/password/reset-confirm",
        ],
    )
    async def test_a_token_carrying_a_lone_surrogate_is_refused(self, client: AsyncClient, path: str, caplog):
        """Anybody can post these, and the answer used to be 500 with a traceback."""
        with caplog.at_level(logging.WARNING):
            answer = await client.post(
                path,
                content='{"token": "\\ud800", "new_password": "An0therPassword!"}',
                headers={"Content-Type": "application/json"},
            )

        assert answer.status_code == 422
        assert not [record for record in caplog.records if record.levelno >= logging.ERROR]

    async def test_a_token_sent_as_a_patch_document_is_refused_too(self, client: AsyncClient, caplog):
        """FastAPI parses any ``application/*+json`` body, so the guard reads those as well."""
        with caplog.at_level(logging.WARNING):
            answer = await client.post(
                "/api/v1/auth/email/verify-confirm",
                content='{"token": "\\ud800"}',
                headers={"Content-Type": "application/merge-patch+json"},
            )

        assert answer.status_code == 422
        assert not [record for record in caplog.records if record.levelno >= logging.ERROR]

    async def test_a_token_sent_without_a_content_type_reaches_no_field(self, client: AsyncClient, caplog):
        """The route binds no body without one, so validation answers rather than the guard."""
        with caplog.at_level(logging.WARNING):
            answer = await client.post("/api/v1/auth/email/verify-confirm", content='{"token": "\\ud800"}')

        assert answer.status_code == 422
        assert answer.json()["detail"] == INVALID_REQUEST_MESSAGE
        assert not [record for record in caplog.records if record.levelno >= logging.ERROR]

    async def test_a_token_carrying_a_nul_is_refused_as_well(self, client: AsyncClient):
        answer = await client.post("/api/v1/auth/email/verify-confirm", json={"token": "a\x00b"})

        assert answer.status_code == 422

    async def test_a_redirect_carrying_a_lone_surrogate_is_refused(self, client: AsyncClient, test_user: dict):
        answer = await client.post(
            "/api/v1/auth/email/verify-request",
            content='{"email": "' + test_user["email"] + '", "redirect_to": "/a\\ud800b"}',
            headers={"Content-Type": "application/json"},
        )

        assert answer.status_code == 422

    async def test_an_emoji_still_goes_through(self, client: AsyncClient, test_user: dict, delivered: list[dict[str, Any]]):
        """An emoji is a surrogate pair in JSON, which is text a column can hold."""
        answer = await client.post(
            "/api/v1/auth/email/verify-request",
            content='{"email": "' + test_user["email"] + '", "redirect_to": "/\\ud83d\\ude00"}',
            headers={"Content-Type": "application/json"},
        )

        assert answer.status_code == 200
        assert [message["kind"] for message in delivered] == ["verify_email"]
