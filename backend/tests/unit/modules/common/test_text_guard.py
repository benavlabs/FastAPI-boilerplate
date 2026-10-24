"""What text a write schema refuses, where in the body it looks for it, and how much it stores."""

import pytest
from pydantic import Field, ValidationError

from src.modules.common.schemas import (
    JSON_MAX_BYTES,
    JSON_MAX_DEPTH,
    NUL,
    EncodableText,
    refuse_oversized_json,
    refuse_unencodable_text,
)

SURROGATE = "\ud800"


class Holder(EncodableText):
    """A write schema carrying text at every depth the guard walks."""

    name: str
    labels: dict[str, str] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)


@pytest.mark.parametrize("unstorable", [f"a{NUL}b", NUL, SURROGATE, f"ok{SURROGATE}"])
def test_a_field_holding_text_no_column_can_store_is_refused(unstorable: str):
    with pytest.raises(ValidationError):
        Holder(name=unstorable)


@pytest.mark.parametrize("unstorable", [f"a{NUL}b", SURROGATE])
def test_the_same_text_is_refused_inside_a_dict_value(unstorable: str):
    with pytest.raises(ValidationError):
        Holder(name="ada", labels={"team": unstorable})


@pytest.mark.parametrize("unstorable", [f"a{NUL}b", SURROGATE])
def test_the_same_text_is_refused_as_a_dict_key(unstorable: str):
    with pytest.raises(ValidationError):
        Holder(name="ada", labels={unstorable: "team"})


@pytest.mark.parametrize("unstorable", [f"a{NUL}b", SURROGATE])
def test_the_same_text_is_refused_inside_a_list(unstorable: str):
    with pytest.raises(ValidationError):
        Holder(name="ada", tags=["fine", unstorable])


def test_text_a_column_can_store_is_accepted():
    held = Holder(name="Ada Lovelace 😀", labels={"team": "platform"}, tags=["fine"])

    assert held.name == "Ada Lovelace 😀"


def test_the_refusal_names_the_field_and_not_the_text():
    """The message reaches the log, where the submitted value does not belong."""
    with pytest.raises(ValueError, match="^password holds a NUL character$"):
        refuse_unencodable_text("password", f"hunter2{NUL}")


def test_a_surrogate_is_still_told_apart_from_a_nul():
    with pytest.raises(ValueError, match="is not valid Unicode"):
        refuse_unencodable_text("name", SURROGATE)


def _nested(levels: int) -> dict:
    """A value nested ``levels`` containers deep, the outermost one included."""
    held: dict = {"a": 1}
    for _ in range(levels - 1):
        held = {"a": held}

    return held


def test_a_value_nested_as_deep_as_the_cap_allows_is_accepted():
    refuse_oversized_json("key_metadata", _nested(JSON_MAX_DEPTH))


def test_a_value_one_level_deeper_is_refused():
    with pytest.raises(ValueError, match=f"nests deeper than {JSON_MAX_DEPTH} levels"):
        refuse_oversized_json("key_metadata", _nested(JSON_MAX_DEPTH + 1))


def test_a_list_nests_the_same_way_a_dict_does():
    nested: list = [1]
    for _ in range(JSON_MAX_DEPTH):
        nested = [nested]

    with pytest.raises(ValueError, match="nests deeper"):
        refuse_oversized_json("key_metadata", {"a": nested})


def test_a_value_deep_enough_to_exhaust_the_stack_is_a_refusal_not_a_crash():
    """``json.dumps`` raises on this one, so the depth has to be read without it."""
    with pytest.raises(ValueError, match="nests deeper"):
        refuse_oversized_json("key_metadata", _nested(2000))


def test_a_value_as_large_as_the_cap_allows_is_accepted():
    """The boundary is the last value stored, not the first refused."""
    refuse_oversized_json("key_metadata", {"a": "x" * (JSON_MAX_BYTES - len('{"a": ""}'))})


def test_non_ascii_text_is_measured_as_the_bytes_it_is_stored_as():
    """This value takes 6,009 bytes stored, and 18,009 with every é escaped as ``\u00e9``."""
    refuse_oversized_json("key_metadata", {"a": "é" * 3000})


def test_a_lone_surrogate_is_measured_rather_than_refused_here():
    """``refuse_unencodable_text`` is what refuses it, naming the field and not the text."""
    refuse_oversized_json("key_metadata", {"a": SURROGATE})


def test_a_value_one_byte_larger_is_refused():
    with pytest.raises(ValueError, match=f"past the {JSON_MAX_BYTES} allowed"):
        refuse_oversized_json("key_metadata", {"a": "x" * (JSON_MAX_BYTES - len('{"a": ""}') + 1)})


def test_the_refusal_names_the_field():
    with pytest.raises(ValueError, match="^key_metadata nests deeper"):
        refuse_oversized_json("key_metadata", _nested(JSON_MAX_DEPTH + 1))
