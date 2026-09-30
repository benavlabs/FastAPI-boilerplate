"""The update schema guards exactly the columns an API-key row requires."""

import pytest
from pydantic import ValidationError

from src.modules.api_keys.models import APIKey
from src.modules.api_keys.schemas import APIKeyUpdate


def _required_columns(model) -> tuple[str, ...]:
    return tuple(
        attribute.key for attribute in model.__mapper__.column_attrs if not any(column.nullable for column in attribute.columns)
    )


def test_the_guarded_names_are_the_models_required_columns():
    assert APIKeyUpdate.NOT_NULLABLE == _required_columns(APIKey)


@pytest.mark.parametrize("field", ["is_active", "permissions", "usage_limits", "name"])
def test_a_required_column_cannot_be_nulled(field: str):
    with pytest.raises(ValidationError, match="cannot be set to null"):
        APIKeyUpdate(**{field: None})


def test_a_nullable_column_still_accepts_null():
    assert APIKeyUpdate(expires_at=None).expires_at is None
