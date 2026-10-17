"""What a key-authenticated request holds, where no other feature is needed to say it.

A permission source is what lets an ordinary account hold anything, and this project's is
the rbac feature. So the cases here are the ones a superuser's key states on its own, plus
the ownership rule a scope doesn't touch. The rest live with the feature they need:
``tests/integration/api_keys_rbac`` and ``tests/integration/api_keys_tiers``.
"""

from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.api_keys.schemas import APIKeyCreate
from src.modules.api_keys.service import APIKeyService
from src.modules.api_keys.transport import API_KEY_HEADER

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("fresh_login_lockout")]

READABLE = "/api/v1/users/"


async def key_for(db_session: AsyncSession, user_id: int, *scope: str, held: frozenset[str] | None = None) -> dict[str, Any]:
    """A key of ``user_id`` scoped to ``scope``, minted as an account that holds it."""
    minted: dict[str, Any] = await APIKeyService().create_api_key(
        user_id=user_id,
        key_data=APIKeyCreate(name="Scoped", permissions=list(scope)),
        db=db_session,
        held=frozenset(scope) if held is None else held,
    )

    return minted


def with_key(key: dict[str, Any]) -> dict[str, str]:
    return {API_KEY_HEADER: key["api_key"]}


def superuser_only(username: str) -> str:
    """A route only a superuser reaches, owned by the accounts feature."""
    return f"/api/v1/users/active-and-inactive/{username}"


async def sign_in(client: AsyncClient, account: dict) -> str:
    """Sign in for real and return the CSRF token for unsafe requests."""
    response = await client.post("/api/v1/auth/login", data={"username": account["username"], "password": account["password"]})
    assert response.status_code == 200, response.text
    token: str = response.json()["csrf_token"]

    return token


async def test_a_key_may_still_edit_its_own_account_unscoped(client: AsyncClient, db_session: AsyncSession, test_user: dict):
    """Ownership is a different axis: a scope narrows permissions, not what an account owns.

    The dangerous self-service routes — the password, the address, closing the account,
    managing keys — take a session and refuse a key outright.
    """
    key = await key_for(db_session, test_user["id"])

    updating = await client.patch(f"/api/v1/users/{test_user['username']}", json={"name": "Renamed"}, headers=with_key(key))

    assert updating.status_code == 200


async def test_a_superusers_key_is_not_a_superuser(client: AsyncClient, db_session: AsyncSession, test_superuser: dict):
    """The flag grants what no scope can name, so a scoped credential never carries it."""
    key = await key_for(db_session, test_superuser["id"], "user.read", held=frozenset({"user.read"}))

    reading = await client.get(READABLE, headers=with_key(key))
    privileged = await client.get(superuser_only(test_superuser["username"]), headers=with_key(key))

    assert reading.status_code == 200
    assert privileged.status_code == 403


async def test_the_superusers_own_session_reaches_the_privileged_route(client: AsyncClient, test_superuser: dict):
    """The control: the refusal above is the key's scope, not the route being unreachable."""
    await sign_in(client, test_superuser)

    assert (await client.get(superuser_only(test_superuser["username"]))).status_code == 200


class TestAKeyCannotEscalateThroughOwnership:
    """``is_self_or_superuser`` reads the acting credential's flag, not the account's row."""

    async def test_a_superusers_key_cannot_edit_another_account(
        self, client: AsyncClient, db_session: AsyncSession, test_superuser: dict, test_user: dict
    ):
        key = await key_for(db_session, test_superuser["id"], "user.read", held=frozenset({"user.read"}))

        edited = await client.patch(
            f"/api/v1/users/{test_user['username']}", json={"name": "Taken Over"}, headers=with_key(key)
        )

        assert edited.status_code == 403

    async def test_the_superusers_own_session_can_edit_it(self, client: AsyncClient, test_superuser: dict, test_user: dict):
        """The control."""
        csrf = await sign_in(client, test_superuser)

        edited = await client.patch(
            f"/api/v1/users/{test_user['username']}", json={"name": "Renamed"}, headers={"X-CSRF-Token": csrf}
        )

        assert edited.status_code == 200
