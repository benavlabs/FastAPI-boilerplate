"""Every collection read is gated, whichever features contributed one.

The paths come from the app itself, so a project that dropped a feature checks
the routes it actually has instead of a list that has to be kept in step.
"""

from typing import Any

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


def _cases(paths: list[str]) -> list[Any]:
    """One case per path, or one skipped case that says why when there are none."""
    if paths:
        return list(paths)

    return [pytest.param(None, marks=pytest.mark.skip(reason="this project has no collection reads under /api/v1/"))]


@pytest.mark.parametrize("path", _cases(COLLECTION_READS))
async def test_read_endpoints_reject_anonymous_callers(client: AsyncClient, path: str):
    """None of the collection reads answer without a session."""
    response = await client.get(path)

    assert response.status_code == 401


async def test_a_project_with_no_collection_reads_says_why_the_rule_is_skipped():
    (case,) = _cases([])
    (mark,) = case.marks

    assert mark.name == "skip"
    assert mark.kwargs["reason"] == "this project has no collection reads under /api/v1/"


async def test_every_api_collection_read_is_covered():
    """A project with API routes must have found some; one with none has nothing to gate."""
    api_routes = [route for route in app.routes if isinstance(route, APIRoute) and route.path.startswith("/api/v1/")]

    assert COLLECTION_READS or not api_routes
