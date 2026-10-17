"""What a caller may ask a list endpoint for, and what order it answers in.

The paths come from the app, so a project checks the listings its features
contributed rather than a list that has to be kept in step.
"""

import pytest
from fastapi.routing import APIRoute
from httpx import AsyncClient

from src.interfaces.main import app

pytestmark = pytest.mark.asyncio

LISTINGS = sorted(
    route.path
    for route in app.routes
    if isinstance(route, APIRoute) and "GET" in route.methods and route.path.endswith("/") and "{" not in route.path
)


@pytest.mark.parametrize("path", LISTINGS)
@pytest.mark.parametrize("query", [{"page": 0}, {"page": -1}, {"items_per_page": 0}, {"items_per_page": 10_000}])
async def test_a_listing_refuses_a_page_it_should_not_serve(superuser_auth_client: AsyncClient, path: str, query: dict):
    """A page of 0 used to be a 500, and an unbounded page size a way to read everything at once."""
    response = await superuser_auth_client.get(path, params=query)

    assert response.status_code == 422


async def test_pages_do_not_overlap(superuser_auth_client: AsyncClient, test_user: dict, test_user_2: dict):
    """Without an order, rows can repeat or vanish between pages."""
    first = await superuser_auth_client.get("/api/v1/users/", params={"page": 1, "items_per_page": 1})
    second = await superuser_auth_client.get("/api/v1/users/", params={"page": 2, "items_per_page": 1})

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["data"][0]["id"] < second.json()["data"][0]["id"]
