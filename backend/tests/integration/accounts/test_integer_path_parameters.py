"""Every route taking a row id in its path refuses one no integer column can hold.

The ids come from the app, so a project sweeps whatever routes its features
contributed rather than naming them.
"""

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from httpx import AsyncClient

from src.interfaces.main import app
from src.modules.common.pagination import MAX_INTEGER_ID

BEYOND_THE_COLUMN = 3000000000
HOLDABLE = 1


def _requests_for(application: FastAPI, row_id: int) -> dict[str, tuple[str, str]]:
    """The method and url of each route taking an integer in its path, once per integer it takes.

    Every other integer in the path carries an id the column holds, so a refusal belongs to
    the one carrying ``row_id`` rather than to whichever is read first.
    """
    requests: dict[str, tuple[str, str]] = {}
    for route in application.routes:
        if not isinstance(route, APIRoute):
            continue

        row_ids = [parameter.name for parameter in route.dependant.path_params if parameter.field_info.annotation is int]
        methods = sorted(route.methods)
        for name in row_ids:
            url = route.path
            for other in row_ids:
                url = url.replace(f"{{{other}}}", str(row_id if other == name else HOLDABLE))

            requests[f"{methods} {route.path} {name}"] = (methods[0], url)

    return requests


def test_the_sweep_reads_an_integer_id_off_a_route():
    """Without this, a project serving no integer id of its own would sweep nothing unnoticed."""
    probe = FastAPI()

    @probe.get("/rows/{row_id}/notes/{name}")
    async def read_a_note(row_id: int, name: str) -> None:  # pragma: no cover - never called
        return None

    assert _requests_for(probe, 7) == {"['GET'] /rows/{row_id}/notes/{name} row_id": ("GET", "/rows/7/notes/{name}")}


@pytest.mark.asyncio
@pytest.mark.parametrize("row_id", [BEYOND_THE_COLUMN, 0])
async def test_every_route_taking_a_row_id_refuses_one_the_column_cannot_hold(superuser_auth_client: AsyncClient, row_id: int):
    """Postgres refuses the query outright, so these answered 500 to anybody holding the permission."""
    for where, (method, url) in _requests_for(app, row_id).items():
        answer = await superuser_auth_client.request(method, url)

        assert answer.status_code == 422, f"{where}: {answer.status_code}"


@pytest.mark.asyncio
async def test_the_largest_id_the_column_holds_still_reaches_the_lookup(superuser_auth_client: AsyncClient):
    """A bound tighter than the column would turn a row a project can hold into a 422."""
    for where, (method, url) in _requests_for(app, MAX_INTEGER_ID).items():
        if method != "GET":
            continue

        answer = await superuser_auth_client.request(method, url)

        assert answer.status_code == 404, f"{where}: {answer.status_code}"
