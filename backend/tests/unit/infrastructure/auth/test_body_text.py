"""The guard in front of crudauth's bodies: what it refuses, and which routes carry it."""

import json
from typing import Annotated, Any

import pytest
from fastapi import Depends, FastAPI, Form
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from src.infrastructure.auth.deps import body_a_database_can_hold
from src.interfaces.main import app

LONE_SURROGATE = '"\\ud800"'
EMOJI = '"\\ud83d\\ude00"'
JSON_HEADERS = {"Content-Type": "application/json"}
A_TOKEN = f'{{"token": {LONE_SURROGATE}}}'


@pytest.fixture
def probe() -> TestClient:
    """An app whose routes take whatever body they are given, behind the guard."""
    application = FastAPI(dependencies=[Depends(body_a_database_can_hold)])

    @application.post("/anything")
    async def anything(payload: Any = None) -> dict[str, str]:
        return {"detail": "taken"}

    @application.post("/a-form")
    async def a_form(name: Annotated[str, Form()]) -> dict[str, str]:
        return {"detail": name}

    return TestClient(application)


@pytest.mark.parametrize(
    "body",
    [
        f'{{"token": {LONE_SURROGATE}}}',
        f'{{"inside": {{"token": {LONE_SURROGATE}}}}}',
        f'{{"inside": [{LONE_SURROGATE}]}}',
        f'{{{LONE_SURROGATE}: "a key"}}',
        '{"token": "a\\u0000b"}',
        LONE_SURROGATE,
    ],
)
def test_text_no_column_can_hold_is_refused(probe: TestClient, body: str):
    answer = probe.post("/anything", content=body, headers=JSON_HEADERS)

    assert answer.status_code == 422


def test_the_refusal_names_the_field_and_not_the_text(probe: TestClient):
    answer = probe.post("/anything", content=f'{{"token": {LONE_SURROGATE}}}', headers=JSON_HEADERS)

    assert answer.json()["detail"] == "token cannot carry text the database cannot store."


def test_a_key_is_refused_without_repeating_it(probe: TestClient):
    """The key is the caller's text, so the refusal names the body rather than the key."""
    answer = probe.post("/anything", content=f'{{{LONE_SURROGATE}: "a key"}}', headers=JSON_HEADERS)

    assert answer.status_code == 422
    assert answer.json()["detail"] == "the body cannot carry text the database cannot store."


@pytest.mark.parametrize(
    "body",
    [f'{{"name": {EMOJI}}}', '{"name": "Ada"}', '{"name": null}', "[]", '""'],
)
def test_text_a_column_can_hold_reaches_the_route(probe: TestClient, body: str):
    answer = probe.post("/anything", content=body, headers=JSON_HEADERS)

    assert answer.status_code == 200
    assert answer.json() == {"detail": "taken"}


@pytest.mark.parametrize(
    "content_type",
    [
        "application/json",
        "application/json; charset=utf-8",
        "APPLICATION/JSON",
        "application/merge-patch+json",
        "application/vnd.api+json",
    ],
)
def test_every_content_type_the_route_reads_as_json_is_read_here_too(probe: TestClient, content_type: str):
    """FastAPI parses any ``application/*+json`` body, so skipping one would walk past the text."""
    answer = probe.post("/anything", content=A_TOKEN, headers={"Content-Type": content_type})

    assert answer.status_code == 422


@pytest.mark.parametrize("content_type", ["text/plain", "application/xml", "application/jsonish"])
def test_a_content_type_the_route_does_not_read_as_json_is_left_alone(probe: TestClient, content_type: str):
    answer = probe.post("/anything", content=A_TOKEN, headers={"Content-Type": content_type})

    assert answer.status_code == 200


def test_a_body_that_is_not_json_is_left_to_the_route(probe: TestClient):
    answer = probe.post("/a-form", data={"name": "Ada"})

    assert answer.status_code == 200
    assert answer.json() == {"detail": "Ada"}


def test_an_empty_body_is_left_to_the_route(probe: TestClient):
    answer = probe.post("/anything", headers=JSON_HEADERS)

    assert answer.status_code == 200


def test_a_body_that_does_not_parse_is_left_to_the_route(probe: TestClient):
    """The guard reads only text it can walk; the probe route takes whatever it is given."""
    answer = probe.post("/anything", content="{not json", headers=JSON_HEADERS)

    assert answer.status_code == 200


def _dependency_calls(route: APIRoute) -> set[Any]:
    """Every dependency the route resolves, at any depth."""
    calls, pending = set(), list(route.dependant.dependencies)
    while pending:
        dependant = pending.pop()
        calls.add(dependant.call)
        pending.extend(dependant.dependencies)

    return calls


GUARDED_ROUTES = [
    route
    for route in app.routes
    if isinstance(route, APIRoute) and route.body_field is not None and not route.path.endswith("/auth/login")
    if route.path.startswith("/api/v1/auth/")
]
"""The account routes that take a body, which is where the library's own models are."""


def test_the_project_mounts_a_route_with_a_body_from_the_library():
    """The sweep below says nothing where nothing is mounted."""
    assert {route.path for route in GUARDED_ROUTES} >= {
        "/api/v1/auth/change-password",
        "/api/v1/auth/email/verify-confirm",
        "/api/v1/auth/password/reset-confirm",
    }


@pytest.mark.parametrize("route", GUARDED_ROUTES, ids=lambda route: route.path)
def test_every_account_route_taking_a_body_carries_the_guard(route: APIRoute):
    assert body_a_database_can_hold in _dependency_calls(route)


@pytest.mark.parametrize("route", GUARDED_ROUTES, ids=lambda route: route.path)
def test_every_account_route_taking_a_body_asks_for_a_content_type(route: APIRoute):
    """A body with no content type reaches no field as text while this holds (fastapi/routing.py)."""
    assert route.strict_content_type is True


def test_the_login_form_is_guarded_by_its_own_dependency():
    """Form fields cannot carry a lone surrogate, and the form guard refuses a NUL."""
    login = next(route for route in app.routes if isinstance(route, APIRoute) and route.path.endswith("/auth/login"))
    names = {call.__name__ for call in _dependency_calls(login) if callable(call)}

    assert "credentials_a_database_can_hold" in names
    assert json.loads(LONE_SURROGATE)  # the escape only JSON carries
