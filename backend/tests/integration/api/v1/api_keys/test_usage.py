"""What a key-authenticated request records, and what its usage limits refuse."""

import logging
import time
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

import src.modules.api_keys.usage as usage_module
from src.infrastructure.auth.setup import auth as crud_auth
from src.modules.api_keys.limits import WINDOWS, counter_key, refusal_key
from src.modules.api_keys.models import APIKey, KeyUsage
from src.modules.api_keys.schemas import APIKeyCreate, KeyUsageCreate
from src.modules.api_keys.service import APIKeyService
from src.modules.api_keys.transport import API_KEY_HEADER, UsedKey
from src.modules.user.models import User
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


async def _counted(api_key_id: int, window: str) -> int:
    """What the limiter has counted for a key's window, in the window running now."""
    limiter = crud_auth.rate_limiter
    assert limiter is not None
    now = int(time.time())
    seconds = WINDOWS[window]
    counted = await limiter.get_count(f"{counter_key(api_key_id, window)}:{now - now % seconds}")

    return counted or 0


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
    """Clear every window a key in this file counts under, the refusals it records included.

    ``increment_and_check`` counts under a window-stamped key, so resetting the bare key
    would leave the live window untouched and carry a filled budget into the next test.
    """
    limiter = crud_auth.rate_limiter
    if limiter is None:
        return

    now = int(time.time())
    for api_key_id in COUNTED_IDS:
        for window, seconds in WINDOWS.items():
            for key in (counter_key(api_key_id, window), refusal_key(api_key_id, window)):
                await limiter.reset(key)
                await limiter.reset(f"{key}:{now - now % seconds}")


@pytest.fixture(autouse=True)
async def clear_counters():
    """The limiter counts in this process for the whole run, so each test starts clean."""
    await _empty_the_windows()

    yield

    await _empty_the_windows()


@pytest.fixture
async def a_clock_that_does_not_move(monkeypatch):
    """The clock the limiter stamps its windows from, held at the second the test starts.

    A window is fixed and aligned to the clock, so a boundary landing between two of a
    test's requests rolls the counters: the next refusal is the first one its window has
    seen, and a count read after it is read under a window the requests never counted in.
    Held still, the window a request counts in and the window a count is read from are the
    same one. The counters are emptied under it on the way in and out, so a window the
    clock was holding open is left to no later test.
    """
    held = float(int(time.time()))
    monkeypatch.setattr(time, "time", lambda: held)
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


class TestWhatTheRecorderIsHandedForTheStamp:
    """``record`` is handed the time the request arrived, and stamps the key with that one."""

    async def test_the_time_it_is_handed_is_the_time_the_key_is_stamped_with(self, db_session: AsyncSession, test_user: dict):
        """Reading the clock here instead would stamp the key with when the write landed."""
        key = await _key(db_session, test_user["id"])
        arrived = datetime.now(UTC) - timedelta(minutes=1)
        usage = KeyUsageCreate(api_key_id=key["id"], user_id=test_user["id"], endpoint=READABLE, method="GET", status_code=200)

        await usage_module.record(UsedKey(key["id"], test_user["id"], "203.0.113.7"), usage, arrived)

        stamped = await db_session.get_one(APIKey, key["id"])
        await db_session.refresh(stamped)

        assert stamped.last_used_at == arrived
        assert stamped.last_used_ip == "203.0.113.7"
        assert [row.status_code for row in await _rows(db_session, key["id"])] == [200]


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

    async def test_a_forwarded_address_no_column_can_hold_is_recorded_as_nothing(
        self, client: AsyncClient, db_session: AsyncSession, test_superuser: dict, monkeypatch
    ):
        """The handler has done its work and committed it by the time the row is built.

        The write is a profile edit, which takes ``user.update`` of a scoped credential: a
        superuser's key can be scoped to it with no permission source configured.
        """
        monkeypatch.setattr(crud_auth.runtime, "trusted_proxy_hops", 1)
        updating = frozenset({"user.update"})
        key = await _key(db_session, test_superuser["id"], held=updating, permissions=sorted(updating))
        owned = f"/api/v1/users/{test_superuser['username']}"

        answered = await client.patch(owned, json={"name": "Renamed"}, headers={**_with(key), "X-Forwarded-For": "a" * 60})

        assert answered.status_code == 200, answered.text
        renamed = await db_session.get_one(User, test_superuser["id"])
        await db_session.refresh(renamed)
        assert renamed.name == "Renamed"
        recorded = await _rows(db_session, key["id"])
        assert [(row.endpoint, row.status_code, row.ip_address) for row in recorded] == [(owned, 200, None)]
        stored = await db_session.get_one(APIKey, key["id"])
        await db_session.refresh(stored)
        assert stored.last_used_ip is None

    async def test_a_forwarded_address_that_is_not_an_address_is_recorded_as_nothing(
        self, client: AsyncClient, db_session: AsyncSession, test_user: dict, monkeypatch
    ):
        """A header the client writes holds whatever the client put in it."""
        monkeypatch.setattr(crud_auth.runtime, "trusted_proxy_hops", 1)
        key = await _key(db_session, test_user["id"])

        answered = await client.get(READABLE, headers={**_with(key), "X-Forwarded-For": "203.0.113.7, not-an-address"})

        assert answered.status_code == 200
        assert [row.ip_address for row in await _rows(db_session, key["id"])] == [None]
        stored = await db_session.get_one(APIKey, key["id"])
        await db_session.refresh(stored)
        assert stored.last_used_ip is None


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

    @pytest.mark.parametrize(
        "stored",
        [{"requests_per_day": 10, "requests_per_minute": 1}, {"requests_per_minute": 1, "requests_per_day": 10}],
    )
    async def test_a_window_that_refuses_leaves_the_longer_windows_uncounted(
        self, client: AsyncClient, db_session: AsyncSession, test_user: dict, stored: dict, a_clock_that_does_not_move
    ):
        """Ten a day and one a minute: the nine refusals must not spend the day's budget.

        The windows are counted shortest first, so which of them the limits were written
        in makes no difference.
        """
        key = await _key(db_session, test_user["id"], usage_limits=stored)

        answers = [(await client.get(READABLE, headers=_with(key))).status_code for _ in range(10)]

        assert answers == [200] + [429] * 9
        assert await _counted(key["id"], "requests_per_minute") == 10
        assert await _counted(key["id"], "requests_per_day") == 1

    async def test_a_refusal_names_the_time_until_the_longest_full_window_rolls(
        self, client: AsyncClient, db_session: AsyncSession, test_user: dict
    ):
        """Two a minute and two a day: the minute refuses, and the day is what is named.

        The two requests the day allows fill both windows, so a client told to come back
        when the minute rolls would be refused again, every minute until the day rolls.
        """
        key = await _key(db_session, test_user["id"], usage_limits={"requests_per_minute": 2, "requests_per_day": 2})
        allowed = [(await client.get(READABLE, headers=_with(key))).status_code for _ in range(2)]

        refused = [await client.get(READABLE, headers=_with(key)) for _ in range(2)]

        assert allowed == [200, 200]
        assert [answer.status_code for answer in refused] == [429, 429]
        assert min(int(answer.headers["Retry-After"]) for answer in refused) > WINDOWS["requests_per_minute"]

    async def test_a_window_records_its_first_refusal_and_not_the_rest(
        self, client: AsyncClient, db_session: AsyncSession, test_user: dict, a_clock_that_does_not_move
    ):
        """A key that spends its window on refusals can see that it did, for one row a window.

        Recording each of them would make a refused request the most expensive one the key
        makes: a row and a stamp for a request the limiter already turned away.
        """
        key = await _key(db_session, test_user["id"], usage_limits={"requests_per_minute": 1})

        answers = [(await client.get(READABLE, headers=_with(key))).status_code for _ in range(5)]

        assert answers == [200, 429, 429, 429, 429]
        assert [row.status_code for row in await _rows(db_session, key["id"])] == [200, 429]

    async def test_the_refusals_it_does_not_record_leave_the_stamp_alone(
        self, client: AsyncClient, db_session: AsyncSession, test_user: dict, a_clock_that_does_not_move
    ):
        """A refusal that writes no row writes no stamp either: the recorder never runs."""
        key = await _key(db_session, test_user["id"], usage_limits={"requests_per_minute": 1})
        await client.get(READABLE, headers=_with(key))
        await client.get(READABLE, headers=_with(key))
        stamped = await db_session.get_one(APIKey, key["id"])
        await db_session.refresh(stamped)
        recorded = stamped.last_used_at

        await client.get(READABLE, headers=_with(key))

        await db_session.refresh(stamped)
        assert stamped.last_used_at == recorded


class TestWhenOneOfTheTwoWritesFails:
    """The stamp and the row are written on their own, so one of them failing keeps the other."""

    async def test_the_row_is_written_when_the_stamp_fails(
        self, client: AsyncClient, db_session: AsyncSession, test_user: dict, monkeypatch, caplog
    ):
        async def unreachable(*args: Any, **kwargs: Any) -> None:
            raise RuntimeError("the stamp went nowhere")

        monkeypatch.setattr(APIKeyService, "note_use", unreachable)
        key = await _key(db_session, test_user["id"])

        with caplog.at_level(logging.ERROR):
            answered = await client.get(READABLE, headers=_with(key))

        assert answered.status_code == 200
        assert [row.status_code for row in await _rows(db_session, key["id"])] == [200]
        assert f"Could not stamp API key {key['id']} as used" in caplog.text

    async def test_the_key_is_stamped_when_the_row_fails(
        self, client: AsyncClient, db_session: AsyncSession, test_user: dict, monkeypatch, caplog
    ):
        async def unreachable(*args: Any, **kwargs: Any) -> None:
            raise RuntimeError("the row went nowhere")

        monkeypatch.setattr(APIKeyService, "record_usage", unreachable)
        key = await _key(db_session, test_user["id"])

        with caplog.at_level(logging.ERROR):
            answered = await client.get(READABLE, headers=_with(key))

        assert answered.status_code == 200
        assert await _rows(db_session, key["id"]) == []
        stamped = await db_session.get_one(APIKey, key["id"])
        await db_session.refresh(stamped)
        assert stamped.last_used_at is not None
        assert f"Could not record usage for API key {key['id']}" in caplog.text
