"""What a key does when its owner's credentials change under it.

A key is not a session, so ending sessions leaves it alone. Recovering an account is
different: whoever reset the password, or claimed the account through a provider, is
taking it back from whoever held it before, keys included.
"""

from typing import Any

import pytest
from crudauth import EmailContext, EmailSender
from crudauth.email.constants import EmailKind
from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.auth.setup import auth as crud_auth
from src.infrastructure.auth.setup import email_config
from src.modules.api_keys.schemas import APIKeyCreate
from src.modules.api_keys.service import APIKeyService
from src.modules.api_keys.transport import API_KEY_HEADER
from src.modules.user.models import User
from tests.fixtures.accounts import reset_recovery_budgets

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("fresh_login_lockout")]

NEW_PASSWORD = "An0therPassword!"
GOOGLE_CALLBACK = "/api/v1/auth/oauth/callback/google"


class _CapturingSender(EmailSender):
    """Keeps every message instead of delivering it."""

    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []

    async def send(self, *, to: str, subject: str, body: str, kind: EmailKind, context: EmailContext) -> None:
        self.sent.append({"to": to, "link": context.link})


@pytest.fixture
def delivered(monkeypatch) -> list[dict[str, Any]]:
    capturing = _CapturingSender()
    monkeypatch.setattr(email_config, "sender", capturing)

    return capturing.sent


@pytest.fixture
async def verified(db_session: AsyncSession, test_user: dict) -> dict:
    """The account with its address verified, which is what minting a key asks for."""
    await db_session.execute(update(User).where(User.id == test_user["id"]).values(email_verified=True))
    await db_session.commit()

    return test_user


async def _mint(db_session: AsyncSession, user_id: int) -> dict[str, Any]:
    minted: dict[str, Any] = await APIKeyService().create_api_key(
        user_id=user_id, key_data=APIKeyCreate(name="Before The Change"), db=db_session
    )

    return minted


def _with(key: dict[str, Any]) -> dict[str, str]:
    return {API_KEY_HEADER: key["api_key"]}


async def _answers(client: AsyncClient, key: dict[str, Any]) -> int:
    """What the key alone answers: a session on the same client would win over it."""
    client.cookies.clear()
    response = await client.get("/api/v1/auth/me", headers=_with(key))

    return response.status_code


async def _reset_the_password(client: AsyncClient, user: dict, delivered: list[dict[str, Any]]) -> None:
    """Drive the real reset flow: request the link, then confirm it."""
    await reset_recovery_budgets(user["email"])
    requested = await client.post("/api/v1/auth/password/reset-request", json={"email": user["email"]})
    assert requested.status_code == 200, requested.text

    token = str(delivered[-1]["link"]).split("token=")[1]
    confirmed = await client.post("/api/v1/auth/password/reset-confirm", json={"token": token, "new_password": NEW_PASSWORD})
    assert confirmed.status_code == 200, confirmed.text


def _stub_google(monkeypatch, profile: dict) -> None:
    provider = crud_auth.oauth_providers["google"]

    async def exchange_code(code, code_verifier=None, headers=None):
        return {"access_token": "google-access-token", "token_type": "Bearer"}

    async def get_user_info(access_token):
        return profile

    monkeypatch.setattr(provider, "exchange_code", exchange_code)
    monkeypatch.setattr(provider, "get_user_info", get_user_info)


async def _claim_through_google(client: AsyncClient, user: dict, monkeypatch) -> None:
    """A provider sign-in on an unverified account claims it, as crudauth's flow does."""
    _stub_google(
        monkeypatch,
        {"sub": "google-claim", "email": user["email"], "email_verified": True, "name": "Claimed Account"},
    )
    started = await client.get("/api/v1/auth/oauth/google", follow_redirects=False)
    assert started.status_code == 307
    state = str(started.headers["location"]).split("state=")[1].split("&")[0]

    callback = await client.get(GOOGLE_CALLBACK, params={"code": "the-code", "state": state}, follow_redirects=False)
    assert callback.status_code == 307
    client.cookies.clear()


async def test_a_key_minted_before_a_password_reset_is_refused_afterwards(
    client: AsyncClient, db_session: AsyncSession, verified: dict, delivered: list[dict[str, Any]]
):
    """Whoever reset the password is taking the account back, from the keys as well."""
    key = await _mint(db_session, verified["id"])
    assert await _answers(client, key) == 200

    await _reset_the_password(client, verified, delivered)

    assert await _answers(client, key) == 401


async def test_a_key_minted_after_a_password_reset_works(
    client: AsyncClient, db_session: AsyncSession, verified: dict, delivered: list[dict[str, Any]]
):
    await _reset_the_password(client, verified, delivered)

    key = await _mint(db_session, verified["id"])

    assert await _answers(client, key) == 200


async def test_a_key_minted_before_a_provider_claimed_the_account_is_refused_afterwards(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, monkeypatch
):
    """The pre-hijack case: a key minted under someone else's address must not survive the claim."""
    key = await _mint(db_session, test_user["id"])
    assert await _answers(client, key) == 200

    await _claim_through_google(client, test_user, monkeypatch)
    claimed = (await db_session.execute(select(User).where(User.id == test_user["id"]))).scalar_one()
    await db_session.refresh(claimed)
    assert claimed.google_id == "google-claim"

    assert await _answers(client, key) == 401


async def test_a_key_minted_before_a_password_change_is_refused_afterwards(
    client: AsyncClient, db_session: AsyncSession, verified: dict
):
    key = await _mint(db_session, verified["id"])
    login = await client.post("/api/v1/auth/login", data={"username": verified["username"], "password": verified["password"]})
    assert login.status_code == 200

    changed = await client.post(
        "/api/v1/auth/change-password",
        json={"current_password": verified["password"], "new_password": NEW_PASSWORD},
        headers={"X-CSRF-Token": login.json()["csrf_token"]},
    )
    assert changed.status_code == 200, changed.text

    assert await _answers(client, key) == 401


async def test_ending_every_session_leaves_the_keys_working(client: AsyncClient, db_session: AsyncSession, verified: dict):
    """A key holds no session, so signing out of every device is not a key revocation."""
    key = await _mint(db_session, verified["id"])
    login = await client.post("/api/v1/auth/login", data={"username": verified["username"], "password": verified["password"]})
    assert login.status_code == 200

    ended = await client.post("/api/v1/auth/logout-all", headers={"X-CSRF-Token": login.json()["csrf_token"]})
    assert ended.status_code == 200, ended.text

    assert await _answers(client, key) == 200


async def test_a_key_cannot_be_minted_until_the_address_is_verified(client: AsyncClient, test_user: dict):
    """An unverified address may belong to somebody else, so it mints nothing."""
    login = await client.post("/api/v1/auth/login", data={"username": test_user["username"], "password": test_user["password"]})
    assert login.status_code == 200

    response = await client.post(
        "/api/v1/api-keys/", json={"name": "From An Unverified Account"}, headers={"X-CSRF-Token": login.json()["csrf_token"]}
    )

    assert response.status_code == 403
    assert "verif" in response.json()["detail"].lower()


async def test_a_verified_account_mints_a_key(client: AsyncClient, verified: dict):
    login = await client.post("/api/v1/auth/login", data={"username": verified["username"], "password": verified["password"]})
    assert login.status_code == 200

    response = await client.post(
        "/api/v1/api-keys/", json={"name": "From A Verified Account"}, headers={"X-CSRF-Token": login.json()["csrf_token"]}
    )

    assert response.status_code == 201, response.text
