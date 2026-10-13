"""Driving the admin panel the way a browser does, and reading back what it streams."""

import csv
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.infrastructure.config.settings import EnvironmentOption, settings
from src.interfaces.admin.auth import EVERY_ADDRESS, LOCKOUT_PREFIX
from src.interfaces.admin.initialize import create_admin_interface
from src.interfaces.admin.lockout import every_address_lockout, panel_lockout

CREDENTIALS = {"username": "admin", "password": "s3cret"}
PROXY = "172.31.240.1"
CLIENT = "203.0.113.7"
OTHER_CLIENT = "198.51.100.9"
PANEL_HOST = "panel.example.com"
PANEL_URL = f"http://{PANEL_HOST}"


def configure_panel(
    monkeypatch,
    username: str = "admin",
    password: str = "s3cret",
    extra_views: tuple[type, ...] = (),
) -> FastAPI:
    """An app with the panel mounted, outside production, behind one trusted proxy.

    ``extra_views`` are added to the panel beside the project's own, for a test that needs a
    view this project doesn't ship, such as one carrying a ``@action``.
    """
    monkeypatch.setattr(settings, "ADMIN_ENABLED", True)
    monkeypatch.setattr(settings, "ADMIN_USERNAME", username)
    monkeypatch.setattr(settings, "ADMIN_PASSWORD", password)
    monkeypatch.setattr(settings, "ENVIRONMENT", EnvironmentOption.LOCAL)
    monkeypatch.setattr(settings, "TRUSTED_PROXY_HOPS", 1)

    app = FastAPI()
    admin = create_admin_interface(app)
    assert admin is not None
    for view in extra_views:
        admin.add_view(view)

    return app


def _counter_keys(address: str, identifier: str) -> tuple[str, ...]:
    """Every key a lockout writes for one address and one identifier."""
    return (
        f"login:ip:{address}",
        f"login:lock:ip:{address}",
        f"login:rounds:ip:{address}",
        f"login:user:{identifier}",
        f"login:lock:user:{identifier}",
        f"login:rounds:user:{identifier}",
        f"login:pair:{address}:{identifier}",
    )


async def clear_admin_lockout(*addresses: str) -> None:
    """Clear what the panel counted against each address, and against every address together."""
    limiter = panel_lockout.backend if panel_lockout is not None else None
    if limiter is not None:
        for address in addresses:
            for key in _counter_keys(address, f"{LOCKOUT_PREFIX}:{address}"):
                await limiter.reset(key)

    panel_wide = every_address_lockout.backend if every_address_lockout is not None else None
    if panel_wide is not None:
        for key in _counter_keys(EVERY_ADDRESS, EVERY_ADDRESS):
            await panel_wide.reset(key)


async def admin_login(app: FastAPI, address: str = CLIENT, **form: str) -> tuple[int, str]:
    """Post the panel's login form as a request that arrived through the proxy.

    Returns the status and whatever ``Set-Cookie`` the response carried: 302 on a login
    sqladmin accepted, 400 on one it refused.
    """
    transport = ASGITransport(app=app, client=(PROXY, 54321))
    async with AsyncClient(transport=transport, base_url="http://test") as caller:
        response = await caller.post(
            "/admin/login",
            data=form or CREDENTIALS,
            headers={"X-Forwarded-For": address},
            follow_redirects=False,
        )

    return response.status_code, response.headers.get("set-cookie", "")


@asynccontextmanager
async def signed_in_panel(app: FastAPI, address: str = CLIENT) -> AsyncIterator[AsyncClient]:
    """A client holding the panel's session cookie, for driving a route the way a page does."""
    transport = ASGITransport(app=app, client=(PROXY, 54321))
    async with AsyncClient(transport=transport, base_url=PANEL_URL) as caller:
        answer = await caller.post(
            "/admin/login",
            data=CREDENTIALS,
            headers={"X-Forwarded-For": address},
            follow_redirects=False,
        )
        assert answer.status_code == 302, answer.status_code

        yield caller


async def exported_rows(view: Any, rows: list[Any]) -> list[list[str]]:
    """Return the parsed lines of ``view``'s CSV export of ``rows``, header first."""
    response = await view.export_data(rows, export_type="csv")
    streamed = [chunk async for chunk in response.body_iterator]
    text = "".join(chunk.decode() if isinstance(chunk, bytes) else chunk for chunk in streamed)

    return list(csv.reader(text.splitlines()))
