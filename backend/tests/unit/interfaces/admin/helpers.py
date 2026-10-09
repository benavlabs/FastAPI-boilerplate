"""Driving the admin panel the way a browser does, and reading back what it streams."""

import csv
from typing import Any

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.infrastructure.auth.setup import auth as crud_auth
from src.infrastructure.config.settings import EnvironmentOption, settings
from src.interfaces.admin.auth import LOCKOUT_PREFIX
from src.interfaces.admin.initialize import create_admin_interface

CREDENTIALS = {"username": "admin", "password": "s3cret"}
PROXY = "172.31.240.1"
CLIENT = "203.0.113.7"
OTHER_CLIENT = "198.51.100.9"


def configure_panel(monkeypatch, username: str = "admin", password: str = "s3cret") -> FastAPI:
    """An app with the panel mounted, outside production, behind one trusted proxy."""
    monkeypatch.setattr(settings, "ADMIN_ENABLED", True)
    monkeypatch.setattr(settings, "ADMIN_USERNAME", username)
    monkeypatch.setattr(settings, "ADMIN_PASSWORD", password)
    monkeypatch.setattr(settings, "ENVIRONMENT", EnvironmentOption.LOCAL)
    monkeypatch.setattr(settings, "TRUSTED_PROXY_HOPS", 1)

    app = FastAPI()
    create_admin_interface(app)

    return app


async def clear_admin_lockout(*addresses: str) -> None:
    """Clear the lockout counted against each address, and against its admin identifier."""
    limiter = crud_auth.rate_limiter
    if limiter is None:
        return

    for address in addresses:
        identifier = f"{LOCKOUT_PREFIX}:{address}"
        for key in (
            f"login:ip:{address}",
            f"login:lock:ip:{address}",
            f"login:rounds:ip:{address}",
            f"login:user:{identifier}",
            f"login:lock:user:{identifier}",
            f"login:rounds:user:{identifier}",
            f"login:pair:{address}:{identifier}",
        ):
            await limiter.reset(key)


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


async def exported_rows(view: Any, rows: list[Any]) -> list[list[str]]:
    """Return the parsed lines of ``view``'s CSV export of ``rows``, header first."""
    response = await view.export_data(rows, export_type="csv")
    streamed = [chunk async for chunk in response.body_iterator]
    text = "".join(chunk.decode() if isinstance(chunk, bytes) else chunk for chunk in streamed)

    return list(csv.reader(text.splitlines()))
