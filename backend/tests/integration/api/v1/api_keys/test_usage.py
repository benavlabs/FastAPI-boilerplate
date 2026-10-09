"""What a key-authenticated request records, and what its usage limits refuse."""

import time
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

import src.modules.api_keys.usage as usage_module
from src.infrastructure.auth.setup import auth as crud_auth
from src.modules.api_keys.limits import WINDOWS, counter_key
from src.modules.api_keys.models import APIKey, KeyUsage
from src.modules.api_keys.schemas import APIKeyCreate
from src.modules.api_keys.service import APIKeyService
from src.modules.api_keys.transport import API_KEY_HEADER
from src.modules.user.service import UserService

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("usage_through_the_test_database")]

READABLE = "/api/v1/auth/me"


async def _key(db_session: AsyncSession, user_id: int, *, held: frozenset[str] = frozenset(), **fields: Any) -> dict[str, Any]:
    minted: dict[str, Any] = await APIKeyService().create_api_key(
        user_id=user_id, key_data=APIKeyCreate(name="Counted", **fields), db=db_session, held=held
    )

    return minted


def _with(key: dict[str, Any]) -> dict[str, str]:
    return {API_KEY_HEADER: key["api_key"]}


async def _rows(db_session: AsyncSession, api_key_id: int) -> list[KeyUsage]:
    stored = await db_session.execute(select(KeyUsage).where(KeyUsage.api_key_id == api_key_id))

    return list(stored.scalars().all())


@pytest.fixture
def usage_through_the_test_database(monkeypatch, db_session: AsyncSession):
    """The recorder opens its own session, which outside a test is the app's engine."""
    monkeypatch.setattr(
        usage_module,
        "local_session",
        async_sessionmaker(bind=db_session.bind, class_=AsyncSession, expire_on_commit=False),
    )


COUNTED_IDS = range(1, 11)
"""Each test gets a fresh database, so key ids repeat while the limiter's counts do not."""


async def _empty_the_windows() -> None:
    """Clear every window a key in this file could be counted under, current one included.

    ``increment_and_check`` counts under a window-stamped key, so resetting the bare key
    would leave the live window untouched and carry a filled budget into the next test.
    """
    limiter = crud_auth.rate_limiter
    if limiter is None:
        return

    now = int(time.time())
    for api_key_id in COUNTED_IDS:
        for window, seconds in WINDOWS.items():
            key = counter_key(api_key_id, window)
            await limiter.reset(key)
            await limiter.reset(f"{key}:{now - now % seconds}")


@pytest.fixture(autouse=True)
async def clear_counters():
    """The limiter counts in this process for the whole run, so each test starts clean."""
    await _empty_the_windows()

    yield

    await _empty_the_windows()


class TestTheUsageRow:
    """One row per request a key authenticated, written after the response."""

    async def test_it_records_the_route_the_method_and_the_status(
        self, client: AsyncClient, db_session: AsyncSession, test_user: dict
    ):
        key = await _key(db_session, test_user["id"])

        answered = await client.get(READABLE, headers=_with(key))

        assert answered.status_code == 200
        recorded = await _rows(db_session, key["id"])
        assert [(row.endpoint, row.method, row.status_code) for row in recorded] == [(READABLE, "GET", 200)]
        assert recorded[0].response_time_ms is not None

    async def test_it_records_the_real_status_of_a_refusal(
        self, client: AsyncClient, db_session: AsyncSession, test_user: dict
    ):
        """A row that always said 200 would make a key's failures invisible.

        An unscoped key reaches the route and is refused by its own scope, so the key is
        authenticated and the refusal is its own.
        """
        key = await _key(db_session, test_user["id"])

        refused = await client.get("/api/v1/users/", headers=_with(key))

        assert refused.status_code == 403
        assert [row.status_code for row in await _rows(db_session, key["id"])] == [403]

    async def test_a_session_only_route_refuses_a_key_whatever_it_records(
        self, client: AsyncClient, db_session: AsyncSession, test_user: dict
    ):
        """The answer is what holds everywhere; the row is not asserted, because it varies.

        A session-only route tries the session transport alone, so nothing there resolves
        the key — unless something else on the route resolves every transport first, which
        the API throttle does when that feature is present. So a row may or may not be
        written, and this asserts only the refusal.
        """
        key = await _key(db_session, test_user["id"])

        refused = await client.get("/api/v1/api-keys/", headers=_with(key))

        assert refused.status_code == 401

    async def test_a_session_request_records_nothing(
        self, client: AsyncClient, db_session: AsyncSession, test_user: dict, fresh_login_lockout
    ):
        await client.post("/api/v1/auth/login", data={"username": test_user["username"], "password": test_user["password"]})

        answered = await client.get(READABLE)

        assert answered.status_code == 200
        assert (await db_session.execute(select(KeyUsage))).scalars().all() == []

    async def test_one_row_per_request(self, client: AsyncClient, db_session: AsyncSession, test_user: dict):
        key = await _key(db_session, test_user["id"])

        for _ in range(3):
            await client.get(READABLE, headers=_with(key))

        assert len(await _rows(db_session, key["id"])) == 3


class TestWhenTheKeyWasLastUsed:
    """``last_used_at`` and ``last_used_ip``, stamped by the recorder after the response.

    The assertions read them straight after the request because httpx's in-process
    transport runs the response's background task before handing the response back. A real
    client sees the answer first and the stamp lands a moment later.
    """

    async def test_they_are_stamped_on_the_row(self, client: AsyncClient, db_session: AsyncSession, test_user: dict):
        key = await _key(db_session, test_user["id"])
        assert (await db_session.get_one(APIKey, key["id"])).last_used_at is None

        await client.get(READABLE, headers=_with(key))

        stored = await db_session.get_one(APIKey, key["id"])
        await db_session.refresh(stored)
        assert stored.last_used_at is not None
        assert stored.last_used_ip == "127.0.0.1"


class TestARowForEveryAnswer:
    """Including the ones the route didn't choose."""

    async def test_a_server_error_is_recorded_as_one(
        self, client: AsyncClient, db_session: AsyncSession, test_superuser: dict, monkeypatch
    ):
        """The catch-all handler turns the exception into a 500 before this middleware sees it.

        Nothing but this test pins that order: the usage middleware has to wrap the
        catch-all, not the other way round, or a key's failures would go unrecorded.
        """

        async def explode(*args, **kwargs):
            raise RuntimeError("boom")

        monkeypatch.setattr(UserService, "get_paginated", explode)
        key = await _key(db_session, test_superuser["id"], permissions=["user.read"], held=frozenset({"user.read"}))

        answered = await client.get("/api/v1/users/", headers=_with(key))

        assert answered.status_code == 500
        assert [row.status_code for row in await _rows(db_session, key["id"])] == [500]


class TestTheAddressRecorded:
    """One address per request: the one the trusted-proxy boundary resolved."""

    async def test_the_client_behind_a_proxy_is_recorded_not_the_proxy(
        self, client: AsyncClient, db_session: AsyncSession, test_user: dict, monkeypatch
    ):
        """``request.client.host`` is the proxy here, so a row carrying it would be wrong."""
        monkeypatch.setattr(crud_auth.runtime, "trusted_proxy_hops", 1)
        key = await _key(db_session, test_user["id"])

        answered = await client.get(READABLE, headers={**_with(key), "X-Forwarded-For": "203.0.113.7"})

        assert answered.status_code == 200
        recorded = await _rows(db_session, key["id"])
        assert [row.ip_address for row in recorded] == ["203.0.113.7"]
        stored = await db_session.get_one(APIKey, key["id"])
        await db_session.refresh(stored)
        assert stored.last_used_ip == "203.0.113.7"


class TestALimitStoredBeforeTheVocabulary:
    """A value the write rules would refuse now is read as it is, and counts for nothing."""

    @pytest.mark.parametrize("stored", [{"requests_per_day": "1000"}, {"plan": "pro"}, {"requests_per_minute": 1.5}])
    async def test_the_key_still_works_and_is_not_counted(
        self, client: AsyncClient, db_session: AsyncSession, test_user: dict, stored: dict
    ):
        key = await _key(db_session, test_user["id"])
        await db_session.execute(update(APIKey).where(APIKey.id == key["id"]).values(usage_limits=stored))
        await db_session.commit()

        answers = [(await client.get(READABLE, headers=_with(key))).status_code for _ in range(3)]

        assert answers == [200, 200, 200]

    async def test_the_owner_can_still_list_it(
        self, client: AsyncClient, db_session: AsyncSession, test_user: dict, auth_client: AsyncClient
    ):
        """A read schema that refused the row would make the key unlistable."""
        key = await _key(db_session, test_user["id"])
        await db_session.execute(update(APIKey).where(APIKey.id == key["id"]).values(usage_limits={"requests_per_day": "1000"}))
        await db_session.commit()

        listed = await auth_client.get("/api/v1/api-keys/")

        assert listed.status_code == 200
        assert [entry["usage_limits"] for entry in listed.json()["data"]] == [{"requests_per_day": "1000"}]


class TestTheUsageLimits:
    """``usage_limits`` counted per key, through the limiter behind the login lockout."""

    async def test_the_boundary_is_the_last_request_allowed(
        self, client: AsyncClient, db_session: AsyncSession, test_user: dict
    ):
        key = await _key(db_session, test_user["id"], usage_limits={"requests_per_minute": 2})

        first = await client.get(READABLE, headers=_with(key))
        second = await client.get(READABLE, headers=_with(key))
        third = await client.get(READABLE, headers=_with(key))

        assert [first.status_code, second.status_code] == [200, 200]
        assert third.status_code == 429
        assert int(third.headers["Retry-After"]) > 0

    async def test_a_key_without_limits_is_not_counted(self, client: AsyncClient, db_session: AsyncSession, test_user: dict):
        key = await _key(db_session, test_user["id"])

        answers = [(await client.get(READABLE, headers=_with(key))).status_code for _ in range(4)]

        assert answers == [200, 200, 200, 200]

    async def test_another_keys_window_is_its_own(self, client: AsyncClient, db_session: AsyncSession, test_user: dict):
        """The counter is keyed by key id, so one key filling up never refuses another."""
        filled = await _key(db_session, test_user["id"], usage_limits={"requests_per_minute": 1})
        other = await _key(db_session, test_user["id"], usage_limits={"requests_per_minute": 1})

        await client.get(READABLE, headers=_with(filled))

        assert (await client.get(READABLE, headers=_with(filled))).status_code == 429
        assert (await client.get(READABLE, headers=_with(other))).status_code == 200

    async def test_a_filled_window_refuses_every_route_the_key_could_reach(
        self, client: AsyncClient, db_session: AsyncSession, test_user: dict
    ):
        """The limit lives in the transport, so it covers routes the API throttle doesn't."""
        key = await _key(db_session, test_user["id"], usage_limits={"requests_per_minute": 1})
        await client.get(READABLE, headers=_with(key))

        unthrottled = await client.get("/api/v1/auth/check-auth", headers=_with(key))

        assert unthrottled.status_code == 429

    async def test_a_stored_limit_no_window_counts_is_left_alone(
        self, client: AsyncClient, db_session: AsyncSession, test_user: dict
    ):
        """A limit stored before the vocabulary existed must not break every request it makes."""
        key = await _key(db_session, test_user["id"], usage_limits={"requests_per_minute": 1})
        await db_session.execute(
            update(APIKey).where(APIKey.id == key["id"]).values(usage_limits={"requests_per_fortnight": 1})
        )
        await db_session.commit()

        answers = [(await client.get(READABLE, headers=_with(key))).status_code for _ in range(3)]

        assert answers == [200, 200, 200]

    async def test_the_refusal_is_recorded_as_well(self, client: AsyncClient, db_session: AsyncSession, test_user: dict):
        """A key that spends its window on refusals can see that it did."""
        key = await _key(db_session, test_user["id"], usage_limits={"requests_per_minute": 1})
        await client.get(READABLE, headers=_with(key))

        await client.get(READABLE, headers=_with(key))

        assert [row.status_code for row in await _rows(db_session, key["id"])] == [200, 429]
