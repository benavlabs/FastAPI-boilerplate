"""Who may read the rate-limit configuration endpoints, and what a name collision answers."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.rate_limit.models import RateLimit

pytestmark = pytest.mark.asyncio


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


async def test_the_named_lookup_is_gated(client: AsyncClient):
    """The by-name lookup is gated too, before the row is even looked up."""
    assert (await client.get("/api/v1/rate-limits/anything")).status_code == 401


async def test_renaming_a_rate_limit_onto_a_taken_name_is_a_conflict(
    superuser_auth_client: AsyncClient, db_session: AsyncSession, test_tier: dict
):
    """A rename onto the name another row holds answers 409, with nothing of the row in it."""
    db_session.add(RateLimit(tier_id=test_tier["id"], name="taken", path="/api/v1/users/", limit=10, period=60))
    db_session.add(RateLimit(tier_id=test_tier["id"], name="renamed", path="/api/v1/tiers/", limit=10, period=60))
    await db_session.flush()

    response = await superuser_auth_client.patch("/api/v1/rate-limits/renamed", json={"name": "taken"})

    assert response.status_code == 409
    assert response.json()["detail"] == "This resource already exists."
