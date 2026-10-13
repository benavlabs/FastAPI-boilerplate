"""The panel's lockout, against what the public login API can write to.

The panel counts its failures against an identifier of its own. crudauth keys the
per-identifier half of the lockout on whatever string reaches ``POST /auth/login``, so
sharing one key space lets anybody lock an operator out by submitting that identifier as
a username.
"""

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import MetaData

from src.infrastructure.auth import limiter
from src.infrastructure.auth.limiter import build_rate_limiter
from src.infrastructure.auth.store import build_store
from src.infrastructure.config.settings import settings
from src.interfaces.admin.auth import LOCKOUT_PREFIX
from src.interfaces.admin.lockout import KEY_PREFIX, build_panel_lockout
from src.interfaces.main import app as api
from tests.unit.interfaces.admin.helpers import (
    CLIENT,
    CREDENTIALS,
    OTHER_CLIENT,
    PROXY,
    admin_login,
    clear_admin_lockout,
    configure_panel,
)

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
async def fresh_lockouts():
    await clear_admin_lockout(CLIENT, OTHER_CLIENT)

    yield

    await clear_admin_lockout(CLIENT, OTHER_CLIENT)


async def _api_logins(username: str, attempts: int) -> list[int]:
    """Fail the public login route ``attempts`` times, as a request through the proxy."""
    transport = ASGITransport(app=api, client=(PROXY, 54321))
    answers = []
    async with AsyncClient(transport=transport, base_url="http://test") as caller:
        for _ in range(attempts):
            response = await caller.post(
                "/api/v1/auth/login",
                data={"username": username, "password": "not-the-password"},
                headers={"X-Forwarded-For": CLIENT},
            )
            answers.append(response.status_code)

    return answers


async def test_the_public_login_api_cannot_lock_the_panel_out(monkeypatch):
    """Submitting the panel's identifier as a username must not reach the panel's budget."""
    monkeypatch.setattr(settings, "TRUSTED_PROXY_HOPS", 1)
    panel = configure_panel(monkeypatch)

    answers = await _api_logins(f"{LOCKOUT_PREFIX}:{CLIENT}", settings.LOGIN_MAX_ATTEMPTS + 2)
    assert 429 in answers, answers

    status, cookie = await admin_login(panel, CLIENT, **CREDENTIALS)

    assert status == 302, status
    assert "admin_session" in cookie


async def test_the_panel_still_locks_itself_out(monkeypatch):
    """The control: the panel's own failures count, and lock it for that address."""
    panel = configure_panel(monkeypatch)

    for _ in range(settings.LOGIN_MAX_ATTEMPTS):
        await admin_login(panel, CLIENT, username="admin", password="wrong")

    status, cookie = await admin_login(panel, CLIENT, **CREDENTIALS)

    assert status == 400
    assert "admin_session" not in cookie


@pytest.mark.parametrize("backend", ["redis", "database"])
async def test_the_panel_counts_under_a_prefix_of_its_own(monkeypatch, backend: str):
    """On a shared server the prefix is the whole of the isolation.

    The suite runs on the memory backend, where a backend object of its own keeps the two
    apart whatever the keys are called. Redis and the counter table are shared, so there
    the keys have to differ by name.
    """
    monkeypatch.setattr(settings, "RATE_LIMITER_BACKEND", backend)
    monkeypatch.setattr(limiter, "database_store", build_store(metadata=MetaData()))

    panel = build_panel_lockout()
    api_limiter = build_rate_limiter()

    assert panel is not None and api_limiter is not None
    assert getattr(panel.backend, "prefix", None) == KEY_PREFIX
    assert getattr(panel.backend, "prefix", None) != getattr(api_limiter, "prefix", None)
