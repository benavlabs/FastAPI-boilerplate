"""No request schema's validation message repeats what was sent.

A ``422`` answers each failure's ``msg``, so a message that quotes the value it refused
hands the caller's input back. The caller already has what it sent; ``loc`` says where.
"""

import types
from typing import Annotated, Any, Union, get_args, get_origin

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from pydantic import BaseModel, ValidationError

from src.interfaces.main import app

SENT_TEXT = "sent-zq7-value"
SENT_NUMBER = -918273645


def _sent(annotation: Any) -> Any:
    """A value of ``annotation``'s shape, every leaf one this test can find again."""
    origin = get_origin(annotation)
    if origin is Annotated:
        return _sent(get_args(annotation)[0])
    if origin in (Union, types.UnionType):
        return _sent(next(arg for arg in get_args(annotation) if arg is not type(None)))
    if origin in (list, set, frozenset, tuple):
        return [_sent(get_args(annotation)[0])] if get_args(annotation) else [SENT_TEXT]
    if origin is dict:
        _, value = get_args(annotation) or (str, str)
        return {SENT_TEXT: _sent(value)}
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return {name: _sent(field.annotation) for name, field in annotation.model_fields.items()}
    if annotation in (int, float) or (isinstance(annotation, type) and issubclass(annotation, int)):
        return SENT_NUMBER

    return SENT_TEXT


def _request_schemas(application: FastAPI) -> list[type[BaseModel]]:
    found = {
        route.body_field.field_info.annotation
        for route in application.routes
        if isinstance(route, APIRoute) and route.body_field is not None
    }

    return sorted(
        (schema for schema in found if isinstance(schema, type) and issubclass(schema, BaseModel)),
        key=lambda schema: schema.__qualname__,
    )


def test_a_route_with_a_json_body_is_found():
    """A project without accounts may have no body to check, so the finder is shown on its own app."""
    application = FastAPI()

    class Widget(BaseModel):
        name: str

    @application.post("/widgets")
    async def create(widget: Widget) -> dict[str, str]:
        return {}

    assert _request_schemas(application) == [Widget]


@pytest.mark.parametrize("schema", _request_schemas(app), ids=lambda schema: schema.__qualname__)
def test_no_failure_message_repeats_what_was_sent(schema: type[BaseModel]):
    try:
        schema.model_validate(_sent(schema))
    except ValidationError as refused:
        messages = [error["msg"] for error in refused.errors()]
    else:
        messages = []

    assert not [message for message in messages if SENT_TEXT in message or str(SENT_NUMBER) in message], messages
