"""What text a write schema refuses, and where in the body it looks for it."""

import pytest
from pydantic import Field, ValidationError

from src.modules.common.schemas import NUL, EncodableText, refuse_unencodable_text

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
