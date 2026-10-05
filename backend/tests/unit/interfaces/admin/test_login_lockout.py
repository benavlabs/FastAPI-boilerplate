"""Failed admin logins are counted per client address, through the panel's own login route."""

import pytest

from src.infrastructure.config.settings import settings
from tests.unit.interfaces.admin.helpers import (
    CLIENT,
    OTHER_CLIENT,
    PROXY,
    admin_login,
    clear_admin_lockout,
    configure_panel,
)

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def panel(monkeypatch):
    """The panel mounted on its own app, with a clean lockout for both test clients."""
    await clear_admin_lockout(CLIENT, OTHER_CLIENT, PROXY)

    yield configure_panel(monkeypatch)

    await clear_admin_lockout(CLIENT, OTHER_CLIENT, PROXY)


async def _fail(panel, address: str = CLIENT) -> int:
    status, _ = await admin_login(panel, address, username="admin", password="wrong")

    return status


async def test_failures_from_one_client_lock_that_client_out(panel):
    """The cap is reached with wrong passwords, and the right one is then refused too."""
    for _ in range(settings.LOGIN_MAX_ATTEMPTS):
        assert await _fail(panel) == 400

    status, cookie = await admin_login(panel, CLIENT)

    assert status == 400
    assert "admin_session" not in cookie


async def test_another_client_behind_the_same_proxy_still_signs_in(panel):
    """Both requests arrive from the proxy's address; the lockout keys on the forwarded one."""
    for _ in range(settings.LOGIN_MAX_ATTEMPTS):
        assert await _fail(panel) == 400

    status, cookie = await admin_login(panel, OTHER_CLIENT)

    assert status == 302
    assert "admin_session" in cookie


async def test_the_right_credentials_are_accepted_below_the_cap(panel):
    for _ in range(settings.LOGIN_MAX_ATTEMPTS - 1):
        assert await _fail(panel) == 400

    status, _ = await admin_login(panel, CLIENT)

    assert status == 302


async def test_a_form_without_a_password_is_refused(panel):
    status, _ = await admin_login(panel, CLIENT, username="admin")

    assert status == 400
