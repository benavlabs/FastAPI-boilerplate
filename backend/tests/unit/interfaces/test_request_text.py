"""Every request body this project defines refuses text no column can hold.

A body model that forgets ``EncodableText`` hands a NUL character or a lone surrogate
straight to the database, which refuses the statement and answers 500.
"""

from fastapi import FastAPI
from fastapi.routing import APIRoute
from pydantic import BaseModel

from src.interfaces.main import app
from src.modules.common.schemas import EncodableText


def _body_models(application: FastAPI, written_in: str = "src.") -> dict[str, type[BaseModel]]:
    """The body model of every route ``application`` serves from ``written_in``, by where it is served.

    crudauth's own routers are mounted here as well; their bodies are the library's to
    validate, so only this project's own models are swept.
    """
    models: dict[str, type[BaseModel]] = {}
    for route in application.routes:
        if not isinstance(route, APIRoute) or route.body_field is None:
            continue

        model = route.body_field.field_info.annotation
        if isinstance(model, type) and issubclass(model, BaseModel) and model.__module__.startswith(written_in):
            models[f"{sorted(route.methods)} {route.path}"] = model

    return models


def test_the_sweep_reads_the_body_model_off_a_route():
    """Without this, a FastAPI that moved the field would leave the sweep below reading nothing.

    A project with every feature removed serves no body of its own, so the sweep cannot
    count on finding one.
    """

    class Body(EncodableText):
        name: str

    probe = FastAPI()

    @probe.post("/probe")
    async def take_a_body(body: Body) -> None:  # pragma: no cover - never called
        return None

    assert _body_models(probe, written_in="tests.") == {"['POST'] /probe": Body}


def test_every_body_this_project_defines_refuses_text_no_column_can_hold():
    for where, model in _body_models(app).items():
        assert issubclass(model, EncodableText), where
