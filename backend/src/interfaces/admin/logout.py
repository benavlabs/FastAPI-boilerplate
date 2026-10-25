"""Signing out of the panel, which takes a POST.

sqladmin serves its logout on ``GET``, and its sidebar links to it, so anything that can
make the operator's browser fetch a URL signs them out: a link from another site, which
``SameSite=Lax`` sends the cookie on. The route below answers a ``GET`` with a form and
clears the session only on the ``POST`` that form sends, which
[SameOriginOnly][src.interfaces.admin.origin.SameOriginOnly] then holds to the panel's own
origin.
"""

from sqladmin import Admin
from starlette.requests import Request
from starlette.responses import HTMLResponse, Response
from starlette.routing import Route

LOGOUT_ROUTE_NAME = "logout"
"""What sqladmin calls the route, which its sidebar builds the link from."""

SIGN_OUT_PAGE = """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Sign out</title>
    <style>
      body {
        margin: 0;
        min-height: 100vh;
        display: grid;
        place-items: center;
        background: #f6f7f9;
        color: #1d242c;
        font: 16px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif;
      }
      form {
        background: #fff;
        border: 1px solid #dbe0e5;
        border-radius: 8px;
        padding: 2rem 2.5rem;
        text-align: center;
      }
      button {
        font: inherit;
        margin-top: 1rem;
        padding: 0.5rem 1.25rem;
        border: 0;
        border-radius: 6px;
        background: #206bc4;
        color: #fff;
        cursor: pointer;
      }
    </style>
  </head>
  <body>
    <form method="post">
      <p>Sign out of the admin panel?</p>
      <button type="submit">Sign out</button>
    </form>
  </body>
</html>
"""


def sign_out_on_a_post_only(admin: Admin) -> None:
    """Replace sqladmin's logout route with one that clears the session on ``POST`` alone.

    Raises:
        RuntimeError: sqladmin serves no route by that name, so nothing was replaced and a
            ``GET`` would still sign out.
    """
    routes = admin.admin.router.routes

    async def sign_out(request: Request) -> Response:
        if request.method == "GET":
            return HTMLResponse(SIGN_OUT_PAGE)

        return await admin.logout(request)

    for index, route in enumerate(routes):
        if getattr(route, "name", None) == LOGOUT_ROUTE_NAME:
            routes[index] = Route("/logout", endpoint=sign_out, name=LOGOUT_ROUTE_NAME, methods=["GET", "POST"])
            return

    raise RuntimeError(f"sqladmin serves no {LOGOUT_ROUTE_NAME!r} route to replace with a POST-only one")
