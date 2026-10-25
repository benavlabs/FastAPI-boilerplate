"""A URL carrying a NUL character is refused before it reaches a route.

``%00`` arrives decoded, so a path parameter or a query value holding one reaches a query,
and Postgres refuses the whole statement: a 500 and a logged traceback for a URL anybody
can send.
"""

import logging

import pytest
from httpx import AsyncClient

from src.modules.common.constants import INVALID_REQUEST_MESSAGE

pytestmark = pytest.mark.asyncio

UNROUTED = "/api/v1/nothing-is-served-here"
"""No route answers this, which is how the refusal is shown to come first."""


@pytest.mark.parametrize(
    "url",
    [
        f"{UNROUTED}/%00",
        f"{UNROUTED}/a%00b",
        f"{UNROUTED}?name=%00",
        f"{UNROUTED}?%00=value",
        f"{UNROUTED}?name=a%00b",
    ],
)
async def test_a_url_carrying_a_nul_is_refused(client: AsyncClient, url: str, caplog):
    with caplog.at_level(logging.WARNING):
        answer = await client.get(url)

    assert answer.status_code == 422
    assert answer.json()["detail"] == INVALID_REQUEST_MESSAGE
    assert answer.json()["support_id"]
    assert "NUL character refused" in caplog.text
    assert not [record for record in caplog.records if record.levelno >= logging.ERROR]


async def test_the_log_names_where_it_came_from_with_the_nul_escaped(client: AsyncClient, caplog):
    """The path is the caller's text, so it reaches the log as a repr rather than raw."""
    with caplog.at_level(logging.WARNING):
        answer = await client.get(f"{UNROUTED}/a%00b")

    assert answer.status_code == 422
    assert "a\\x00b" in caplog.text


async def test_a_post_carrying_one_is_refused_too(client: AsyncClient):
    answer = await client.post(f"{UNROUTED}/%00", json={"name": "ada"})

    assert answer.status_code == 422


async def test_a_url_without_one_is_left_alone(client: AsyncClient):
    """The guard answers for the NUL and nothing else, so this reaches the router."""
    answer = await client.get(f"{UNROUTED}?name=ada")

    assert answer.status_code == 404
