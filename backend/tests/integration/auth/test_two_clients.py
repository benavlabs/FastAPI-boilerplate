"""The two signed-in client fixtures are two users, at the same time, in one test."""

from httpx import AsyncClient


async def test_each_client_is_signed_in_as_its_own_user(
    auth_client: AsyncClient, auth_client_2: AsyncClient, test_user: dict, test_user_2: dict
):
    first = await auth_client.get("/api/v1/users/me")
    second = await auth_client_2.get("/api/v1/users/me")

    assert first.status_code == second.status_code == 200
    assert first.json()["id"] == test_user["id"]
    assert second.json()["id"] == test_user_2["id"]


async def test_signing_one_client_out_leaves_the_other_signed_in(
    auth_client: AsyncClient, auth_client_2: AsyncClient, test_user: dict
):
    signed_out = await auth_client_2.post("/api/v1/auth/logout")

    assert signed_out.status_code == 200
    assert (await auth_client_2.get("/api/v1/users/me")).status_code == 401
    assert (await auth_client.get("/api/v1/users/me")).json()["id"] == test_user["id"]
