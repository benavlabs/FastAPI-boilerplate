"""A key reading another account's tier and rate limits, which both go by ownership.

These need api_keys for the credential and the tier_limits feature for the two routes.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.integration.api.v1.api_keys.test_effective_permissions import key_for, sign_in, with_key

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("fresh_login_lockout")]


async def test_a_superusers_key_cannot_read_another_accounts_tier_or_limits(
    client: AsyncClient, db_session: AsyncSession, test_superuser: dict, test_user: dict
):
    """Both routes read the acting credential's flag, not the account's row."""
    key = await key_for(db_session, test_superuser["id"], "user.read", held=frozenset({"user.read"}))

    tier = await client.get(f"/api/v1/users/{test_user['username']}/tier", headers=with_key(key))
    limits = await client.get(f"/api/v1/users/{test_user['username']}/rate-limits", headers=with_key(key))

    assert tier.status_code == 403
    assert limits.status_code == 403


async def test_the_superusers_own_session_can_read_them(client: AsyncClient, test_superuser: dict, test_user: dict):
    """The control."""
    await sign_in(client, test_superuser)

    tier = await client.get(f"/api/v1/users/{test_user['username']}/tier")
    limits = await client.get(f"/api/v1/users/{test_user['username']}/rate-limits")

    assert tier.status_code == 200
    assert limits.status_code == 200
