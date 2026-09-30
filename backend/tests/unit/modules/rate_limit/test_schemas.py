"""The path a rate limit is stored for: the route template, as the router declares it."""

import pytest
from pydantic import ValidationError

from src.modules.rate_limit.models import RateLimit
from src.modules.rate_limit.schemas import RateLimitCreate, RateLimitRead, RateLimitUpdate


def _create(path: str) -> RateLimitCreate:
    return RateLimitCreate(path=path, limit=5, period=60)


@pytest.mark.parametrize(
    "path",
    ["/api/v1/users", "/api/v1/users/", "/api/v1/users/{username}", "/files/{filepath:path}"],
)
def test_a_route_template_is_accepted(path: str):
    assert _create(path).path == path


@pytest.mark.parametrize("path", ["/api/v1/users/{", "/api/v1/users}", "/api/v1/{a}{b}", "api/v1/users", "/api//v1"])
def test_a_malformed_path_is_refused(path: str):
    with pytest.raises(ValidationError, match="valid API path format|forward slash"):
        _create(path)


def test_an_update_validates_the_path_the_same_way():
    assert RateLimitUpdate(path="/api/v1/users/{username}").path == "/api/v1/users/{username}"

    with pytest.raises(ValidationError, match="valid API path format"):
        RateLimitUpdate(path="/api/v1/users/{")


def _required_columns(model) -> tuple[str, ...]:
    return tuple(
        attribute.key for attribute in model.__mapper__.column_attrs if not any(column.nullable for column in attribute.columns)
    )


def test_the_guarded_names_are_the_models_required_columns():
    assert RateLimitUpdate.NOT_NULLABLE == _required_columns(RateLimit)


def test_a_required_column_cannot_be_nulled():
    with pytest.raises(ValidationError, match="cannot be set to null"):
        RateLimitUpdate(path=None)


def test_reading_a_row_the_app_already_holds_is_not_validated_as_input():
    """A row stored before the path format was tightened must still serialize."""
    row = RateLimitRead(id=1, tier_id=2, name="legacy", path="/api/v1/users/42", limit=5, period=60)

    assert row.path == "/api/v1/users/42"
    assert RateLimitRead(id=1, tier_id=2, name="odd", path="/a{", limit=0, period=0).limit == 0
