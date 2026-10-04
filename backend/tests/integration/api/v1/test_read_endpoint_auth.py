"""Every collection read is gated, whichever features contributed one.

The paths come from the app itself, so a project that dropped a feature checks
the routes it actually has instead of a list that has to be kept in step.
"""

import pytest
from fastapi.routing import APIRoute
from httpx import AsyncClient

from src.interfaces.main import app

pytestmark = pytest.mark.asyncio

COLLECTION_READS = sorted(
    route.path
    for route in app.routes
    if isinstance(route, APIRoute) and "GET" in route.methods and route.path.endswith("/") and route.path.startswith("/api/v1/")
)


@pytest.mark.parametrize("path", COLLECTION_READS)
async def test_read_endpoints_reject_anonymous_callers(client: AsyncClient, path: str):
    """None of the collection reads answer without a session."""
    response = await client.get(path)

    assert response.status_code == 401


async def test_every_api_collection_read_is_covered():
    """A project with API routes must have found some; one with none has nothing to gate."""
    api_routes = [route for route in app.routes if isinstance(route, APIRoute) and route.path.startswith("/api/v1/")]

    assert COLLECTION_READS or not api_routes
