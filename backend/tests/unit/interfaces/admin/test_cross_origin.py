"""What another site can drive at a signed-in panel, which is nothing that changes state.

sqladmin has no CSRF token, so the panel's defence is the cookie's ``SameSite=Strict`` and
a guard that refuses an unsafe method the browser says started somewhere else.
"""

import pytest
from sqladmin import ModelView, action
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response

from src.interfaces.admin.auth import AdminAuth, RootPathSessionMiddleware
from src.interfaces.admin.origin import SameOriginOnly, changes_state
from src.modules.user.models import User
from tests.unit.interfaces.admin.helpers import (
    CLIENT,
    OTHER_CLIENT,
    PANEL_URL,
    admin_login,
    clear_admin_lockout,
    configure_panel,
    signed_in_panel,
)


class ActionProbe(ModelView, model=User):
    """A view carrying the kind of bulk action the guides show, which sqladmin serves on a GET.

    sqladmin names the route from the model, so the action sits at ``/user/action/run``.
    """

    name = "Probe"

    @action(name="run", label="Run")
    async def run(self, request: Request) -> Response:
        return PlainTextResponse("the action ran")


ACTION_URL = "/admin/user/action/run?pks=1"


ANOTHER_SITE = {"Origin": "https://evil.example.com", "Sec-Fetch-Site": "same-site"}
"""A sibling subdomain's form post, which ``SameSite=Lax`` alone would let through."""

THE_PANEL_ITSELF = {"Origin": PANEL_URL, "Sec-Fetch-Site": "same-origin"}


@pytest.fixture
async def panel(monkeypatch):
    """The panel mounted on its own app, with a clean lockout for both test clients."""
    await clear_admin_lockout(CLIENT, OTHER_CLIENT)

    yield configure_panel(monkeypatch, extra_views=(ActionProbe,))

    await clear_admin_lockout(CLIENT, OTHER_CLIENT)


async def test_a_post_to_a_view_from_another_site_is_refused(panel):
    """The refusal comes before routing, so the view's own work never starts."""
    async with signed_in_panel(panel) as caller:
        refused = await caller.post("/admin/user/create", data={"name": "x"}, headers=ANOTHER_SITE)

    assert refused.status_code == 403


async def test_another_site_cannot_sign_the_operator_out(panel):
    async with signed_in_panel(panel) as caller:
        refused = await caller.post("/admin/logout", headers=ANOTHER_SITE, follow_redirects=False)
        still_in = await caller.get("/admin/", follow_redirects=False)

    assert refused.status_code == 403
    assert still_in.status_code == 200


async def test_the_panel_s_own_form_still_posts(panel):
    async with signed_in_panel(panel) as caller:
        accepted = await caller.post("/admin/logout", headers=THE_PANEL_ITSELF, follow_redirects=False)
        signed_out = await caller.get("/admin/", follow_redirects=False)

    assert accepted.status_code == 302
    assert signed_out.status_code == 302
    assert "/admin/login" in signed_out.headers["location"]


async def test_an_origin_naming_the_host_the_request_arrived_at_is_the_panel_s_own(panel):
    """What a browser too old to send ``Sec-Fetch-Site`` leaves to go on."""
    async with signed_in_panel(panel) as caller:
        accepted = await caller.post("/admin/logout", headers={"Origin": PANEL_URL}, follow_redirects=False)

    assert accepted.status_code == 302


async def test_an_origin_naming_another_host_is_refused_without_sec_fetch_site(panel):
    async with signed_in_panel(panel) as caller:
        refused = await caller.post("/admin/logout", headers={"Origin": "https://evil.example.com"}, follow_redirects=False)

    assert refused.status_code == 403


async def test_a_caller_sending_neither_header_is_allowed(panel):
    """curl and scripts send no origin at all, and no site can make a browser do that."""
    async with signed_in_panel(panel) as caller:
        accepted = await caller.post("/admin/logout", follow_redirects=False)

    assert accepted.status_code == 302


async def test_an_action_another_site_links_to_does_not_run(panel):
    """sqladmin serves every ``@action`` on a GET, and a sibling subdomain is the same site."""
    async with signed_in_panel(panel) as caller:
        refused = await caller.get(ACTION_URL, headers=ANOTHER_SITE)

    assert refused.status_code == 403
    assert "the action ran" not in refused.text


async def test_the_panel_s_own_page_still_runs_the_action(panel):
    async with signed_in_panel(panel) as caller:
        ran = await caller.get(ACTION_URL, headers=THE_PANEL_ITSELF)

    assert ran.status_code == 200
    assert ran.text == "the action ran"


async def test_a_page_from_another_site_may_still_read_what_a_get_answers(panel):
    """Safe methods are left alone, so a link into the panel still works."""
    async with signed_in_panel(panel) as caller:
        answered = await caller.get("/admin/", headers=ANOTHER_SITE, follow_redirects=False)

    assert answered.status_code == 200


async def test_the_admin_cookie_travels_on_nothing_another_site_starts(panel):
    status, cookie = await admin_login(panel, CLIENT)

    assert status == 302
    assert "samesite=strict" in cookie.casefold()


@pytest.mark.parametrize(
    ("method", "path", "held"),
    [
        ("POST", "/user/create", True),
        ("DELETE", "/user/delete", True),
        ("GET", "/user/action/run", True),
        ("HEAD", "/user/action/run", True),
        ("GET", "/user/list", False),
        ("GET", "/user/details/1", False),
        ("GET", "/user/export/csv", False),
        ("GET", "/action/list", False),
    ],
)
def test_which_requests_are_held_to_the_panel_s_own_origin(method: str, path: str, held: bool):
    """Paths are the ones under the panel's mount, so a model called ``Action`` keeps its pages."""
    assert changes_state(method, path) is held


def test_the_guard_stands_in_front_of_the_panel_s_session():
    """Every request passes it, including the ones the session middleware would reject."""
    mounted: list[Middleware] = AdminAuth(secret_key="a-secret", base_url="/admin").middlewares

    assert [middleware.cls for middleware in mounted] == [SameOriginOnly, RootPathSessionMiddleware]
