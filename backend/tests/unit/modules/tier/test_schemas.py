"""The update schema guards exactly the columns a tier row requires."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from src.modules.tier.models import Tier
from src.modules.tier.schemas import TierRead, TierUpdate


def _required_columns(model) -> tuple[str, ...]:
    return tuple(
        attribute.key for attribute in model.__mapper__.column_attrs if not any(column.nullable for column in attribute.columns)
    )


def test_the_guarded_names_are_the_models_required_columns():
    assert TierUpdate.NOT_NULLABLE == _required_columns(Tier)


def test_a_required_column_cannot_be_nulled():
    with pytest.raises(ValidationError, match="cannot be set to null"):
        TierUpdate(name=None)


def test_reading_a_row_the_app_already_holds_is_not_validated_as_input():
    row = TierRead(id=1, name="", created_at=datetime.now(UTC))

    assert row.name == ""
