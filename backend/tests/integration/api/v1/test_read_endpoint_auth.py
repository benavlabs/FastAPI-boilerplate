"""Who may read the tier and rate-limit endpoints."""

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio

ANONYMOUS_READS = [
    "/api/v1/users/",
    "/api/v1/tiers/",
    "/api/v1/rate-limits/",
]


@pytest.mark.parametrize("path", ANONYMOUS_READS)
async def test_read_endpoints_reject_anonymous_callers(client: AsyncClient, path: str):
    """None of the collection reads answer without a session."""
    response = await client.get(path)

    assert response.status_code == 401


async def test_named_reads_reject_anonymous_callers(client: AsyncClient, test_tier: dict):
    """The by-name lookups are gated too, before the row is even looked up."""
    assert (await client.get(f"/api/v1/tiers/{test_tier['name']}")).status_code == 401
    assert (await client.get("/api/v1/rate-limits/anything")).status_code == 401


async def test_tiers_are_readable_by_any_signed_in_user(auth_client: AsyncClient, test_tier: dict):
    """Tiers describe what a plan offers, so any signed-in user may read them."""
    listing = await auth_client.get("/api/v1/tiers/")
    named = await auth_client.get(f"/api/v1/tiers/{test_tier['name']}")

    assert listing.status_code == 200
    assert named.status_code == 200
    assert named.json()["name"] == test_tier["name"]


async def test_rate_limit_configuration_is_superuser_only(auth_client: AsyncClient):
    """Rate-limit rows are operational configuration, not user-facing data."""
    assert (await auth_client.get("/api/v1/rate-limits/")).status_code == 403
    assert (await auth_client.get("/api/v1/rate-limits/anything")).status_code == 403


async def test_rate_limits_are_readable_by_a_superuser(superuser_auth_client: AsyncClient):
    """A superuser reads the same rows that PATCH and DELETE already required one for."""
    response = await superuser_auth_client.get("/api/v1/rate-limits/")

    assert response.status_code == 200
    assert "data" in response.json()


@pytest.mark.parametrize(
    ("path", "method", "expected"),
    [
        ("/api/v1/users/{username}", "get", {"401", "404"}),
        ("/api/v1/tiers/", "get", {"401"}),
        ("/api/v1/tiers/{name}", "get", {"401", "404"}),
        ("/api/v1/rate-limits/", "get", {"401", "403"}),
        ("/api/v1/rate-limits/{name}", "get", {"401", "403", "404"}),
    ],
)
async def test_openapi_advertises_the_gate(client: AsyncClient, path: str, method: str, expected: set[str]):
    """A client generated from the schema must know these can be refused."""
    schema = (await client.get("/openapi.json")).json()
    operation = schema["paths"][path][method]

    assert expected <= set(operation["responses"])


async def test_a_missing_rate_limit_says_so(superuser_auth_client: AsyncClient):
    """The 404 names what wasn't found, without echoing the requested name back."""
    response = await superuser_auth_client.get("/api/v1/rate-limits/no-such-limit")

    assert response.status_code == 404
    body = response.json()
    assert body["detail"] == "Rate limit configuration not found."
    assert "no-such-limit" not in response.text
    assert body["support_id"]
