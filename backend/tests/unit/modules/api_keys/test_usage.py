"""What the recorder makes of a request before anything is written."""

import asyncio
import logging
from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from starlette.applications import Starlette
from starlette.background import BackgroundTask
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route

import src.modules.api_keys.usage as usage_module
from src.modules.api_keys.schemas import KeyUsageCreate
from src.modules.api_keys.transport import UsedKey
from src.modules.api_keys.usage import KeyUsageMiddleware, _address

STAMPED_KEY = 7


HANDLER_TIME = timedelta(milliseconds=50)
"""How long the slow route below takes, which is the gap the arrival time is read before."""


def _app(client_ip: str | None = "127.0.0.1", takes: timedelta = timedelta(), sets: BackgroundTask | None = None) -> Starlette:
    """A route stamped the way the transport stamps a request it authenticated."""

    async def handled(request: Request) -> Response:
        request.state.api_key_id = STAMPED_KEY
        request.state.api_key_user_id = 1
        request.state.api_key_client_ip = client_ip
        await asyncio.sleep(takes.total_seconds())

        return Response("handled", background=sets)

    return Starlette(
        routes=[Route("/", handled, methods=["GET", "PROPFIND"])],
        middleware=[Middleware(KeyUsageMiddleware)],
    )


@pytest.fixture
def handed(monkeypatch) -> list[tuple[UsedKey, KeyUsageCreate, datetime]]:
    """What the middleware handed the writer, which opens a session of its own."""
    collected: list[tuple[UsedKey, KeyUsageCreate, datetime]] = []

    async def collect(used: UsedKey, usage: KeyUsageCreate, used_at: datetime) -> None:
        collected.append((used, usage, used_at))

    monkeypatch.setattr(usage_module, "record", collect)

    return collected


async def _request(app: Starlette, method: str = "GET"):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        return await client.request(method, "/")


@pytest.mark.parametrize(
    ("resolved", "recorded"),
    [
        ("203.0.113.7", "203.0.113.7"),
        ("2001:db8::1", "2001:db8::1"),
        ("::ffff:203.0.113.7", "::ffff:203.0.113.7"),
        ("a" * 60, None),
        ("not-an-address", None),
        ("unknown", None),
        ("fe80::1%" + "a" * 60, None),
        ("", None),
        (None, None),
    ],
)
def test_an_address_is_recorded_as_it_came_or_not_at_all(resolved: str | None, recorded: str | None):
    """A forwarding header is the client's to write, so what it holds may be anything."""
    assert _address(resolved) == recorded


@pytest.mark.asyncio
async def test_what_the_writer_is_handed_for_a_request_it_can_record(handed):
    answered = await _request(_app())

    assert answered.status_code == 200
    used, usage, _ = handed[0]
    assert (used.api_key_id, used.owner_id, used.client_ip) == (STAMPED_KEY, 1, "127.0.0.1")
    assert (usage.endpoint, usage.method, usage.status_code, usage.ip_address) == ("/", "GET", 200, "127.0.0.1")


@pytest.mark.asyncio
async def test_an_address_no_column_can_hold_is_handed_over_as_none(handed):
    """Both writes take it: the row's address and the stamp on the key itself."""
    answered = await _request(_app("a" * 60))

    assert answered.status_code == 200
    used, usage, _ = handed[0]
    assert (used.client_ip, usage.ip_address) == (None, None)


@pytest.mark.asyncio
async def test_a_method_no_row_can_hold_leaves_the_answer_alone_and_is_logged(handed, caplog):
    """A project is free to serve a method the usage schema never heard of."""
    with caplog.at_level(logging.ERROR):
        answered = await _request(_app(), "PROPFIND")

    assert answered.status_code == 200
    assert answered.text == "handled"
    assert handed == []
    assert f"Could not describe usage for API key {STAMPED_KEY}" in caplog.text


@pytest.mark.asyncio
async def test_the_writer_is_handed_the_time_the_request_arrived(handed):
    """The key is stamped with that time, so a write landing late cannot move it back.

    Handing over the time the write runs instead would put the stamp a request's length
    later, which is this route's own time.
    """
    before = datetime.now(UTC)

    answered = await _request(_app(takes=HANDLER_TIME))

    after = datetime.now(UTC)
    assert answered.status_code == 200
    _, _, used_at = handed[0]
    assert before <= used_at <= after - HANDLER_TIME


@pytest.mark.asyncio
async def test_a_task_the_route_set_runs_as_well_as_the_recording(handed):
    """Attaching the recording must not cost a route its own task.

    It cannot: the recording goes on the response this middleware streams, and the route's
    task goes on the route's own response, which runs it where the route is called.
    """
    ran: list[str] = []

    answered = await _request(_app(sets=BackgroundTask(ran.append, "the route's own task")))

    assert answered.status_code == 200
    assert ran == ["the route's own task"]
    assert len(handed) == 1


@pytest.mark.asyncio
async def test_a_task_the_route_set_cannot_cost_the_recording(handed):
    """The route's task runs after the recording, so what it raises leaves the row written."""

    def unreachable() -> None:
        raise RuntimeError("the route's task went nowhere")

    with pytest.raises(RuntimeError, match="went nowhere"):
        await _request(_app(sets=BackgroundTask(unreachable)))

    assert len(handed) == 1
