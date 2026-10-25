"""Every route taking text in its path answers 422 to a NUL character in it.

The guard sits in front of the router, so this sweeps whatever routes the project
carries rather than naming them.
"""

import pytest
from fastapi.routing import APIRoute
from httpx import AsyncClient

from src.interfaces.main import app

pytestmark = pytest.mark.asyncio


def _urls_with_a_nul() -> dict[str, str]:
    """Each route that takes text in its path, with ``%00`` standing in for that text."""
    urls: dict[str, str] = {}
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue

        text_parameters = [
            parameter.name for parameter in route.dependant.path_params if parameter.field_info.annotation is str
        ]
        if not text_parameters:
            continue

        url = route.path
        for name in text_parameters:
            url = url.replace(f"{{{name}}}", "%00")

        urls[f"{sorted(route.methods)} {route.path}"] = url

    return urls


async def test_every_route_taking_text_in_its_path_refuses_a_nul(client: AsyncClient, test_user: dict):
    """Signed in, so a refusal is the guard's rather than the authentication's."""
    await client.post(
        "/api/v1/auth/login",
        data={"username": test_user["username"], "password": test_user["password"]},
    )
    urls = _urls_with_a_nul()

    assert urls
    for where, url in urls.items():
        answer = await client.get(url)

        assert answer.status_code == 422, f"{where}: {answer.status_code}"
