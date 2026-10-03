"""An API key's expiry must carry an offset, so it can be compared with the stored one."""

import logging
from typing import Any

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def _create(auth_client: AsyncClient, **extra: str) -> dict[str, Any]:
    response = await auth_client.post("/api/v1/api-keys/", json={"name": "Expiring Key", **extra})
    assert response.status_code == 201, response.text
    created: dict[str, Any] = response.json()

    return created


async def test_a_naive_expiry_is_refused_on_create(auth_client: AsyncClient, caplog):
    with caplog.at_level(logging.WARNING):
        response = await auth_client.post("/api/v1/api-keys/", json={"name": "Naive Key", "expires_at": "2030-01-01T00:00:00"})

    assert response.status_code == 422
    assert "'expires_at'" in caplog.text
    assert "timezone_aware" in caplog.text


async def test_an_aware_expiry_is_accepted_on_create(auth_client: AsyncClient):
    created = await _create(auth_client, expires_at="2030-01-01T00:00:00+00:00")

    assert created["expires_at"].startswith("2030-01-01T00:00:00")


async def test_a_naive_expiry_is_refused_on_update(auth_client: AsyncClient, caplog):
    created = await _create(auth_client, expires_at="2030-01-01T00:00:00+00:00")

    with caplog.at_level(logging.WARNING):
        response = await auth_client.patch(f"/api/v1/api-keys/{created['id']}", json={"expires_at": "2029-01-01T00:00:00"})

    assert response.status_code == 422
    assert "'expires_at'" in caplog.text
    assert "timezone_aware" in caplog.text


async def test_an_aware_expiry_shortening_the_key_is_accepted(auth_client: AsyncClient):
    created = await _create(auth_client, expires_at="2030-01-01T00:00:00+00:00")

    response = await auth_client.patch(f"/api/v1/api-keys/{created['id']}", json={"expires_at": "2029-01-01T00:00:00+00:00"})

    assert response.status_code == 200, response.text


async def test_an_expiry_no_offset_can_hold_is_refused(auth_client: AsyncClient):
    """The last date a datetime holds, moved west, lands past it."""
    response = await auth_client.post(
        "/api/v1/api-keys/",
        json={"name": "Far Future", "expires_at": "9999-12-31T23:59:59-05:00"},
    )

    assert response.status_code == 422


async def test_the_last_expiry_utc_can_hold_is_accepted(auth_client: AsyncClient):
    created = await _create(auth_client, expires_at="9999-12-31T23:59:59+00:00")

    assert created["expires_at"].startswith("9999-12-31")


async def test_an_expiry_no_offset_can_hold_is_refused_on_an_update(auth_client: AsyncClient):
    created = await _create(auth_client, expires_at="2030-01-01T00:00:00+00:00")

    response = await auth_client.patch(
        f"/api/v1/api-keys/{created['id']}",
        json={"expires_at": "9999-12-31T23:59:59-05:00"},
    )

    assert response.status_code == 422
