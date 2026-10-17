"""Who may read the tier endpoints."""

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def test_named_reads_reject_anonymous_callers(client: AsyncClient, test_tier: dict):
    """The by-name lookup is gated too, before the row is even looked up."""
    assert (await client.get(f"/api/v1/tiers/{test_tier['name']}")).status_code == 401


async def test_tiers_are_readable_by_any_signed_in_user(auth_client: AsyncClient, test_tier: dict):
    """Tiers describe what a plan offers, so any signed-in user may read them."""
    listing = await auth_client.get("/api/v1/tiers/")
    named = await auth_client.get(f"/api/v1/tiers/{test_tier['name']}")

    assert listing.status_code == 200
    assert named.status_code == 200
    assert named.json()["name"] == test_tier["name"]


@pytest.mark.parametrize(
    ("path", "method", "expected"),
    [
        ("/api/v1/tiers/", "get", {"401"}),
        ("/api/v1/tiers/{name}", "get", {"401", "404"}),
    ],
)
async def test_openapi_advertises_the_gate(client: AsyncClient, path: str, method: str, expected: set[str]):
    """A client generated from the schema must know these can be refused."""
    schema = (await client.get("/openapi.json")).json()
    operation = schema["paths"][path][method]

    assert expected <= set(operation["responses"])
