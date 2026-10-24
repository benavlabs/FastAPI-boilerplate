"""Signing out of the panel, which a GET no longer does.

sqladmin serves logout on ``GET`` and links to it from every page, so anything that made
the operator's browser fetch that URL signed them out.
"""

import pytest
from fastapi import FastAPI

from src.interfaces.admin.initialize import create_admin_interface
from src.interfaces.admin.logout import LOGOUT_ROUTE_NAME, sign_out_on_a_post_only
from tests.unit.interfaces.admin.helpers import (
    CLIENT,
    clear_admin_lockout,
    configure_panel,
    signed_in_panel,
)


@pytest.fixture
async def panel(monkeypatch):
    """The panel mounted on its own app, with a clean lockout for the test client."""
    await clear_admin_lockout(CLIENT)

    yield configure_panel(monkeypatch)

    await clear_admin_lockout(CLIENT)


async def test_a_get_answers_a_form_and_leaves_the_session_alone(panel):
    async with signed_in_panel(panel) as caller:
        page = await caller.get("/admin/logout", follow_redirects=False)
        still_in = await caller.get("/admin/", follow_redirects=False)

    assert page.status_code == 200
    assert 'method="post"' in page.text
    assert still_in.status_code == 200


async def test_the_form_this_page_carries_signs_out(panel):
    async with signed_in_panel(panel) as caller:
        signed_out = await caller.post("/admin/logout", follow_redirects=False)
        after = await caller.get("/admin/", follow_redirects=False)

    assert signed_out.status_code == 302
    assert after.status_code == 302
    assert "/admin/login" in after.headers["location"]


async def test_the_sidebar_link_still_resolves(panel):
    """sqladmin builds it from the route's name, which the replacement keeps."""
    async with signed_in_panel(panel) as caller:
        page = await caller.get("/admin/", follow_redirects=False)

    assert page.status_code == 200
    assert "/admin/logout" in page.text


def test_a_panel_whose_logout_route_went_missing_is_refused(monkeypatch):
    """An sqladmin that no longer serves it must fail loudly, not leave a GET signing out."""
    configure_panel(monkeypatch)
    admin = create_admin_interface(FastAPI())
    assert admin is not None
    admin.admin.router.routes = [
        route for route in admin.admin.router.routes if getattr(route, "name", None) != LOGOUT_ROUTE_NAME
    ]

    with pytest.raises(RuntimeError, match=LOGOUT_ROUTE_NAME):
        sign_out_on_a_post_only(admin)
