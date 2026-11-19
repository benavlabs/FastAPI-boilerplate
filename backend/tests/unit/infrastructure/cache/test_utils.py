import pytest
from crudauth import Principal
from starlette.datastructures import QueryParams

from src.infrastructure.cache import utils
from src.infrastructure.cache.utils import (
    caller_marks,
    format_extra_data,
    format_prefix,
    format_query,
)

DECLARED = {"page", "items_per_page"}


def test_the_query_is_the_declared_parameters_sorted():
    assert format_query(QueryParams("page=2&items_per_page=20"), DECLARED) == "items_per_page=20&page=2"


def test_a_parameter_the_route_does_not_declare_is_left_out():
    """It cannot have changed the answer, so it stores no answer of its own."""
    assert format_query(QueryParams("page=2&utm_source=newsletter"), DECLARED) == "page=2"


def test_a_name_that_spells_the_delimiters_is_escaped():
    """One parameter, named with an escaped pair. Written as it came it reads back as two."""
    crafted = QueryParams("items_per_page%3D20%26page=1")
    assert crafted.multi_items() == [("items_per_page=20&page", "1")]

    assert format_query(crafted, {"items_per_page=20&page"}) == "items_per_page%3D20%26page=1"


def test_a_session_is_marked_by_the_account_it_signed_in_as():
    assert caller_marks(Principal(user_id=7, transport="session")) == "7"


def test_a_principal_is_marked_by_its_account_and_the_fingerprint_wired(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(utils, "SCOPE_FINGERPRINT", lambda principal: "narrowed")

    assert caller_marks(Principal(user_id=7, transport="apikey", scopes=("user.read",))) == "7/narrowed"


def test_without_a_fingerprint_wired_a_principal_is_marked_by_its_account(monkeypatch: pytest.MonkeyPatch):
    """A project without accounts wires none, and has no credential that carries a scope."""
    monkeypatch.setattr(utils, "SCOPE_FINGERPRINT", None)

    assert caller_marks(Principal(user_id=7, transport="apikey", scopes=("user.read",))) == "7"


def test_an_account_read_any_other_way_is_marked_with_nothing():
    """It says nothing about which of the account's credentials asked, so it is no caller.

    Keyed on a current-user mapping, a key scoped to reading and its owner's session would
    both be stored under the account, and one would be served what the other asked for.
    """

    class _Caller:
        user_id = 3

    assert caller_marks({"id": 3, "username": "alice"}) is None
    assert caller_marks(_Caller()) is None


def test_no_caller_is_marked_with_nothing():
    assert caller_marks(None) is None


def test_format_prefix_simple():
    prefix = "user"
    kwargs = {"user_id": 123}
    formatted = format_prefix(prefix, kwargs)
    assert formatted == "user"


def test_format_prefix_with_variables():
    prefix = "user:{user_id}:profile"
    kwargs = {"user_id": 123, "other_param": "value"}
    formatted = format_prefix(prefix, kwargs)
    assert formatted == "user:123:profile"


def test_format_prefix_with_multiple_variables():
    prefix = "org:{org_id}:user:{user_id}"
    kwargs = {"org_id": 456, "user_id": 123}
    formatted = format_prefix(prefix, kwargs)
    assert formatted == "org:456:user:123"


def test_format_extra_data_simple():
    extra_data = {"user": "user_id"}
    kwargs = {"user_id": 123}
    formatted = format_extra_data(extra_data, kwargs)
    assert formatted == {"user": 123}


def test_format_extra_data_multiple():
    extra_data = {"user": "user_id", "org": "org_id"}
    kwargs = {"user_id": 123, "org_id": 456}
    formatted = format_extra_data(extra_data, kwargs)
    assert formatted == {"user": 123, "org": 456}


def test_format_extra_data_missing_key():
    extra_data = {"user": "user_id", "org": "org_id"}
    kwargs = {"user_id": 123}
    formatted = format_extra_data(extra_data, kwargs)
    assert formatted == {"user": 123}
    assert "org" not in formatted
