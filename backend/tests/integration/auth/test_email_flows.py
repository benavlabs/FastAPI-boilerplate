"""The recovery flows crudauth mounts: verification, password reset, email change.

crudauth owns the tokens and the rules; these drive the mounted routes with a sender
that keeps what it was asked to deliver, and hold the behaviour this project relies on.
"""

from typing import Any

import pytest
import pytest_asyncio
from crudauth import EmailContext, EmailSender
from crudauth.email.constants import EmailKind
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.auth.setup import email_config
from src.infrastructure.config.settings import settings
from src.interfaces.main import app
from src.modules.user.models import User
from tests.fixtures.accounts import reset_recovery_budgets

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("fresh_login_lockout")]

NEW_PASSWORD = "An0therPassword!"
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


class TestChangingAnAddress:
    """The new address confirms the change, and the old one is told about it."""

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
