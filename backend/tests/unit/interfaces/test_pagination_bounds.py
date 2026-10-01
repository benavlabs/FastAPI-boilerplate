"""Every listing takes its page bounds from one place."""

from fastapi.routing import APIRoute
from pydantic.fields import FieldInfo

from src.interfaces.main import app
from src.modules.common.pagination import MAX_ITEMS_PER_PAGE


def _page_size_fields() -> dict[str, FieldInfo]:
    fields: dict[str, FieldInfo] = {}
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        for parameter in route.dependant.query_params:
            if parameter.name == "items_per_page":
                fields[f"{route.path} {parameter.name}"] = parameter.field_info

    return fields


def test_every_listing_caps_its_page_at_the_shared_bound():
    fields = _page_size_fields()

    for where, field_info in fields.items():
        bounds = {metadata.__class__.__name__: metadata for metadata in field_info.metadata}
        assert bounds["Le"].le == MAX_ITEMS_PER_PAGE, where
        assert bounds["Ge"].ge == 1, where
