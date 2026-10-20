"""How long the panel honours a session, and what stops it honouring one.

Starlette re-signs the cookie whenever something writes to the session, which starts its
``Max-Age`` and its signature's clock again, so neither is a cap. What bounds a session is
what the session carries: when it was issued, and a fingerprint of the credentials it was
issued against.
"""

import hashlib
from time import time
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from sqladmin import Flash, ModelView, action
from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response

from src.infrastructure.config.settings import settings
from src.interfaces.admin import auth
from src.interfaces.admin.auth import (
    AUTHENTICATED,
    FINGERPRINT,
    ISSUED_AT,
    SESSION_MAX_AGE_SECONDS,
    AdminAuth,
)
from src.modules.user.models import User
from tests.unit.interfaces.admin.helpers import (
    CLIENT,
    PANEL_URL,
    PROXY,
    clear_admin_lockout,
    configure_panel,
    signed_in_panel,
)

SAME_ORIGIN = {"Sec-Fetch-Site": "same-origin"}


class FlashProbe(ModelView, model=User):
    """A view whose action leaves a flashed message behind, as sqladmin invites one to.

    sqladmin's metaclass takes ``identity`` from the model, overwriting one set in the class
    body, so the probe claims its own below and keeps its routes off the project's user view.
    """

    name = "Flash probe"

    @action(name="flash", label="Flash")
    async def flash_a_message(self, request: Request) -> Response:
        Flash.success(request, "the action ran")

        return PlainTextResponse("flashed")


FlashProbe.identity = "flash-probe"

FLASH_URL = f"/admin/{FlashProbe.identity}/action/flash"


@pytest.fixture
async def panel(monkeypatch):
    """The panel mounted on its own app, with a clean lockout for the test client."""
    await clear_admin_lockout(CLIENT)

    yield configure_panel(monkeypatch, extra_views=(FlashProbe,))

    await clear_admin_lockout(CLIENT)


def issued(monkeypatch, seconds_ago: float) -> None:
    """Make the next login stamp its session that long ago."""
    stamp = time() - seconds_ago
    monkeypatch.setattr(auth, "time", lambda: stamp)


async def test_a_session_just_inside_the_cap_is_honoured(panel, monkeypatch):
    issued(monkeypatch, SESSION_MAX_AGE_SECONDS - 300)

    async with signed_in_panel(panel) as caller:
        monkeypatch.setattr(auth, "time", time)
        answered = await caller.get("/admin/", follow_redirects=False)

    assert answered.status_code == 200


async def test_a_session_past_the_cap_is_refused_however_lately_its_cookie_was_resigned(panel, monkeypatch):
    """A flashed message writes to the session, which hands the cookie a fresh ``Max-Age``."""
    issued(monkeypatch, SESSION_MAX_AGE_SECONDS - 300)

    async with signed_in_panel(panel) as caller:
        monkeypatch.setattr(auth, "time", time)
        flashed = await caller.get(FLASH_URL, headers=SAME_ORIGIN)
        monkeypatch.setattr(auth, "time", lambda: time() + 600)
        refused = await caller.get("/admin/", follow_redirects=False)

    assert flashed.status_code == 200
    assert f"Max-Age={SESSION_MAX_AGE_SECONDS}" in flashed.headers.get("set-cookie", "")
    assert refused.status_code == 302
    assert "/admin/login" in refused.headers["location"]


async def test_a_session_from_before_a_password_change_is_refused(panel, monkeypatch):
    async with signed_in_panel(panel) as caller:
        monkeypatch.setattr(settings, "ADMIN_PASSWORD", "a-new-password")
        refused = await caller.get("/admin/", follow_redirects=False)

    assert refused.status_code == 302
    assert "/admin/login" in refused.headers["location"]


async def test_a_session_from_before_a_username_change_is_refused(panel, monkeypatch):
    async with signed_in_panel(panel) as caller:
        monkeypatch.setattr(settings, "ADMIN_USERNAME", "someone-else")
        refused = await caller.get("/admin/", follow_redirects=False)

    assert refused.status_code == 302


async def test_the_refused_session_is_cleared_rather_than_left_to_be_sent_again(panel, monkeypatch):
    async with signed_in_panel(panel) as caller:
        monkeypatch.setattr(settings, "ADMIN_PASSWORD", "a-new-password")
        refused = await caller.get("/admin/", follow_redirects=False)

    cleared = refused.headers.get("set-cookie", "")

    assert "admin_session=null" in cleared
    assert "01 Jan 1970" in cleared


@pytest.mark.parametrize("carries", ["neither", "no issue time", "no fingerprint"])
async def test_a_session_missing_either_thing_that_bounds_it_is_refused(carries: str):
    """``neither`` is what a cookie an earlier version signed decodes to."""
    backend = AdminAuth(secret_key="a-secret", base_url="/admin")
    session: dict = {AUTHENTICATED: True}
    if carries == "no issue time":
        session[FINGERPRINT] = backend.credentials_fingerprint()
    if carries == "no fingerprint":
        session[ISSUED_AT] = int(time())

    honoured = await backend.authenticate(Request({"type": "http", "headers": [], "session": session}))

    assert honoured is False
    assert session == {}


async def test_a_session_outlives_a_restart_while_the_credentials_hold(monkeypatch):
    """The fingerprint is drawn from ``SECRET_KEY`` and the credentials, not from the process."""
    await clear_admin_lockout(CLIENT)
    first = configure_panel(monkeypatch)
    restarted = configure_panel(monkeypatch)

    async with signed_in_panel(first) as caller:
        cookies = caller.cookies

    transport = ASGITransport(app=restarted, client=(PROXY, 54321))
    async with AsyncClient(transport=transport, base_url=PANEL_URL, cookies=cookies) as caller:
        answered = await caller.get("/admin/", follow_redirects=False)

    await clear_admin_lockout(CLIENT)

    assert answered.status_code == 200


def test_the_fingerprint_changes_with_either_credential(monkeypatch):
    backend = AdminAuth(secret_key="a-secret", base_url="/admin")
    monkeypatch.setattr(settings, "ADMIN_USERNAME", "admin")
    monkeypatch.setattr(settings, "ADMIN_PASSWORD", "s3cret")
    configured = backend.credentials_fingerprint()

    monkeypatch.setattr(settings, "ADMIN_PASSWORD", "s3crets")
    with_another_password = backend.credentials_fingerprint()
    monkeypatch.setattr(settings, "ADMIN_PASSWORD", "s3cret")
    monkeypatch.setattr(settings, "ADMIN_USERNAME", "root")
    with_another_username = backend.credentials_fingerprint()

    assert len({configured, with_another_password, with_another_username}) == 3
    assert "s3cret" not in configured
    assert AdminAuth(secret_key="another-secret", base_url="/admin").credentials_fingerprint() != configured


def test_the_fingerprint_is_derived_from_the_credentials_with_a_work_factor(monkeypatch):
    """A cookie carries it, so a fast hash would be one a word list could be run against.

    Whoever holds the cookie and ``SECRET_KEY`` holds everything the derivation was made
    from apart from the password itself.
    """
    derived: list[tuple[bytes, bytes, int]] = []
    real_scrypt = hashlib.scrypt

    def recording(password: bytes, **parameters: Any) -> bytes:
        derived.append((password, parameters["salt"], parameters["n"]))

        return real_scrypt(password, **parameters)

    monkeypatch.setattr(hashlib, "scrypt", recording)
    monkeypatch.setattr(settings, "ADMIN_USERNAME", "admin")
    monkeypatch.setattr(settings, "ADMIN_PASSWORD", "a-work-factor")
    auth._derived.cache_clear()

    fingerprint = AdminAuth(secret_key="a-secret", base_url="/admin").credentials_fingerprint()

    assert derived == [(b"admin:a-work-factor", b"a-secret", 2**14)]
    assert "a-work-factor" not in fingerprint


def test_the_derivation_is_made_as_the_panel_is_built_and_not_again(monkeypatch):
    """The panel compares the fingerprint on every request, and deriving one is slow.

    Built before the panel serves anything, so no request holds the loop for it.
    """
    derivations = 0
    real_scrypt = hashlib.scrypt

    def counting(password: bytes, **parameters: Any) -> bytes:
        nonlocal derivations
        derivations += 1

        return real_scrypt(password, **parameters)

    monkeypatch.setattr(hashlib, "scrypt", counting)
    monkeypatch.setattr(settings, "ADMIN_USERNAME", "admin")
    monkeypatch.setattr(settings, "ADMIN_PASSWORD", "derived-once")
    auth._derived.cache_clear()

    backend = AdminAuth(secret_key="a-secret", base_url="/admin")

    assert derivations == 1
    assert len({backend.credentials_fingerprint() for _ in range(3)}) == 1
    assert derivations == 1
