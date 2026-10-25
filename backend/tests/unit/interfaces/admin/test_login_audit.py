"""What a refused admin panel login leaves in the log, through the panel's own login route.

The panel answers a door of its own, outside crudauth's routes and its hooks, so the lines
are written where the panel refuses rather than by ``on_login_failed``.
"""

import logging

import pytest

from src.infrastructure.auth.audit import UNKNOWN_IDENTIFIER
from src.infrastructure.config.settings import settings
from src.interfaces.admin.auth import DOOR, EVERY_ADDRESS_DOOR
from tests.unit.interfaces.admin.helpers import (
    CLIENT,
    OTHER_CLIENT,
    admin_login,
    clear_admin_lockout,
    configure_panel,
)

pytestmark = pytest.mark.asyncio

SPRAY = tuple(f"203.0.113.{40 + offset}" for offset in range(6))
"""More addresses than the panel lets spend a budget each, so the shared budget runs out."""


@pytest.fixture
async def panel(monkeypatch):
    """The panel mounted on its own app, with a clean lockout for every test client."""
    await clear_admin_lockout(CLIENT, OTHER_CLIENT, *SPRAY)

    yield configure_panel(monkeypatch)

    await clear_admin_lockout(CLIENT, OTHER_CLIENT, *SPRAY)


async def test_a_wrong_password_on_the_configured_username_records_it_with_the_caller(panel, caplog):
    with caplog.at_level(logging.WARNING):
        await admin_login(panel, CLIENT, username="admin", password="wrong")

    assert f"login refused at {DOOR}: 'admin'" in caplog.text
    assert CLIENT in caplog.text
    assert "invalid_credentials" in caplog.text


async def test_a_username_the_panel_has_none_of_is_never_written_out(panel, caplog):
    """The username box is where a password lands when someone types one box too high."""
    with caplog.at_level(logging.WARNING):
        await admin_login(panel, CLIENT, username="hunter2!", password="wrong")

    assert "hunter2" not in caplog.text
    assert UNKNOWN_IDENTIFIER in caplog.text
    assert CLIENT in caplog.text


async def test_the_lockout_on_one_address_records_how_long_it_refuses_for(panel, caplog):
    for _ in range(settings.LOGIN_MAX_ATTEMPTS):
        await admin_login(panel, CLIENT, username="admin", password="wrong")

    with caplog.at_level(logging.WARNING):
        await admin_login(panel, CLIENT)

    assert f"login locked out at {DOOR} for {settings.LOGIN_LOCKOUT_BASE_SECONDS}s" in caplog.text
    assert CLIENT in caplog.text


async def test_the_panel_closing_to_every_address_says_so(panel, caplog):
    """The two lockouts refuse the same way, and only the log says which budget ran out."""
    for address in SPRAY:
        for _ in range(settings.LOGIN_MAX_ATTEMPTS):
            await admin_login(panel, address, username="admin", password="wrong")

    with caplog.at_level(logging.WARNING):
        await admin_login(panel, OTHER_CLIENT)

    assert f"login locked out at {EVERY_ADDRESS_DOOR} for" in caplog.text
    assert OTHER_CLIENT in caplog.text
