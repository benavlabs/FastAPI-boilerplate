"""Failed admin logins are counted per client address and across them all, through the panel's login route."""

import pytest

from src.infrastructure.config.settings import settings
from src.interfaces.admin.lockout import ADDRESS_BUDGETS
from tests.unit.interfaces.admin.helpers import (
    CLIENT,
    OTHER_CLIENT,
    PROXY,
    admin_login,
    clear_admin_lockout,
    configure_panel,
)

pytestmark = pytest.mark.asyncio

SPRAY = tuple(f"203.0.113.{20 + offset}" for offset in range(6))
"""More addresses than the panel lets spend a budget each, every one of them within its own."""

UNSEEN = "203.0.113.90"
"""An address the panel has counted nothing against."""


@pytest.fixture
async def panel(monkeypatch):
    """The panel mounted on its own app, with a clean lockout for every test client."""
    await clear_admin_lockout(CLIENT, OTHER_CLIENT, PROXY, UNSEEN, *SPRAY)

    yield configure_panel(monkeypatch)

    await clear_admin_lockout(CLIENT, OTHER_CLIENT, PROXY, UNSEEN, *SPRAY)


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


async def test_failures_spread_over_many_addresses_close_the_panel_to_all_of_them(panel):
    """One password stands behind the panel, so the budget every address shares is what bounds guessing."""
    for address in SPRAY:
        for _ in range(settings.LOGIN_MAX_ATTEMPTS):
            assert await _fail(panel, address) == 400

    status, cookie = await admin_login(panel, UNSEEN)

    assert status == 400
    assert "admin_session" not in cookie


async def test_one_address_hammering_cannot_spend_the_budget_the_others_share(panel):
    """Its attempts past its own lockout are refused before they are counted against every address."""
    for _ in range(settings.LOGIN_MAX_ATTEMPTS * len(SPRAY)):
        assert await _fail(panel) == 400

    status, cookie = await admin_login(panel, OTHER_CLIENT)

    assert status == 302
    assert "admin_session" in cookie


async def test_signing_in_over_and_over_does_not_close_the_panel(panel):
    """The shared budget counts failures: a correct password gives back the attempt it made."""
    for _ in range(settings.LOGIN_MAX_ATTEMPTS * ADDRESS_BUDGETS + 1):
        status, _ = await admin_login(panel, CLIENT)

        assert status == 302
