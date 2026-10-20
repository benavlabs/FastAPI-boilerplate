import re
from collections.abc import Collection
from typing import Any
from urllib.parse import urlencode

from crudauth import Principal
from fastapi.dependencies.utils import get_flat_dependant
from pydantic import BaseModel
from starlette.requests import Request

from ..auth.scope import scope_fingerprint


def extract_data_inside_brackets(input_string: str) -> list[str]:
    """Extract data inside curly brackets from a given string.

    Args:
        input_string: The input string containing data in curly brackets.

    Returns:
        A list of strings found inside curly brackets.
    """
    data_inside_brackets = re.findall(r"{(.*?)}", input_string)
    return data_inside_brackets


def construct_data_dict(data_inside_brackets: list[str], kwargs: dict[str, Any]) -> dict[str, Any]:
    """Construct a dictionary based on data inside brackets and keyword arguments.

    Args:
        data_inside_brackets: A list of keys found inside brackets.
        kwargs: A dictionary of keyword arguments.

    Returns:
        A dictionary with keys from data_inside_brackets and values from kwargs.
    """
    data_dict = {}
    for key in data_inside_brackets:
        if key not in kwargs:
            continue
        data_dict[key] = kwargs[key]
    return data_dict


def format_prefix(prefix: str, kwargs: dict[str, Any]) -> str:
    """Format a prefix using keyword arguments.

    Args:
        prefix: The prefix template to format.
        kwargs: A dictionary of keyword arguments.

    Returns:
        The formatted prefix.
    """
    data_inside_brackets = extract_data_inside_brackets(prefix)
    data_dict = construct_data_dict(data_inside_brackets, kwargs)
    formatted_prefix = prefix.format(**data_dict)
    return formatted_prefix


def format_extra_data(to_invalidate_extra: dict[str, str], kwargs: dict[str, Any]) -> dict[str, Any]:
    """Format extra data for cache invalidation.

    Args:
        to_invalidate_extra: A dictionary of cache key prefixes and ID templates.
        kwargs: A dictionary of keyword arguments.

    Returns:
        A dictionary of formatted prefixes and IDs.
    """
    formatted_extra = {}
    for prefix, id_name in to_invalidate_extra.items():
        if id_name in kwargs:
            formatted_extra[prefix] = kwargs[id_name]
            continue

        if "{" in id_name:
            id_vars = extract_data_inside_brackets(id_name)
            if not id_vars:
                continue

            id_var = id_vars[0]
            if id_var in kwargs:
                formatted_id = id_name.format(**{id_var: kwargs[id_var]})
                formatted_extra[prefix] = formatted_id

    return formatted_extra


def format_query(query_params: Any, declared: Collection[str] | None) -> str:
    """The query a request carried, as the parameters ``declared`` names, sorted and escaped.

    Only what the route declares decides its answer, so a parameter it never reads is left
    out rather than stored under a key of its own. ``declared`` of ``None`` is for a route
    whose parameters could not be read, and keeps every one of them: a key too many costs
    a request its cache, where a key too few answers one request with another's response.

    Escaping is what keeps a name or a value holding a ``&`` or an ``=`` from reading as
    the parameters it spells: written as it came, ``items_per_page%3D20%26page=1`` is one
    parameter that reads back as two.
    """
    items = query_params.multi_items() if hasattr(query_params, "multi_items") else query_params
    carried = items if declared is None else [(name, value) for name, value in items if name in declared]

    return urlencode(sorted(carried))


def caller_marks(caller: Any) -> str | None:
    """How the caller a route resolved is written into a key, or ``None`` for anything else.

    Only a principal will do, because only a principal brings its credential with it: one
    that carries a scope holds less than the account behind it, and two of them hold
    different things, so the scope is part of what the response was made for. An account
    read any other way, a current-user mapping among them, says nothing about which of its
    credentials asked, and a route keyed on that would serve a session's response to a key.
    """
    if not isinstance(caller, Principal):
        return None

    narrowed = scope_fingerprint(caller)

    return str(caller.user_id) if narrowed is None else f"{caller.user_id}/{narrowed}"


DECLARED_QUERY_NAMES = "_declared_query_names"
"""Where the names a route declares are kept once read, which is on the route itself."""


def _names_of(parameter: Any) -> set[str]:
    """What a declared query parameter is read under: its own name, or a model's fields.

    A parameter annotated with a model carries the query in that model's fields, and is
    itself named after the argument it lands in, which no query ever carries.
    """
    annotation = getattr(parameter.field_info, "annotation", None)
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return {field.alias or name for name, field in annotation.model_fields.items()}

    return {parameter.alias}


def declared_query_names(request: Request) -> frozenset[str] | None:
    """The query parameters the route this request matched declares, under the names it reads.

    Taken from the route rather than from the arguments it was called with: a parameter
    carrying an alias arrives under the alias and lands in an argument of another name, and
    one a dependency or a model reads is no argument of the route at all, so the arguments
    would leave all of those out of the key and every page of such a listing would share
    one entry.

    ``None`` where there is no route to read it from, which keeps every parameter the
    request carried rather than none of them.

    Read once and kept on the route, because walking a dependency tree is not work for
    every request.
    """
    route = request.scope.get("route")
    if route is None or getattr(route, "dependant", None) is None:
        return None

    kept: frozenset[str] | None = route.__dict__.get(DECLARED_QUERY_NAMES)
    if kept is None:
        declared = get_flat_dependant(route.dependant).query_params
        kept = frozenset(name for parameter in declared for name in _names_of(parameter))
        route.__dict__[DECLARED_QUERY_NAMES] = kept

    return kept


def build_cache_key(prefix: str, resource_id: Any, query: str, caller_id: str | None) -> str:
    """The key one response is stored under.

    The query and the caller are part of it, so a cached page can't be served for another
    page, and one caller's response can't be served to another. A write passes no query:
    what it invalidates is the entry for the resource, not the entry for its own
    parameters, and every page of a listing needs a pattern.
    """
    parts = [prefix]
    if resource_id is not None:
        parts.append(str(resource_id))
    if query:
        parts.append(f"q={query}")
    if caller_id is not None:
        parts.append(f"u={caller_id}")

    return ":".join(parts)
