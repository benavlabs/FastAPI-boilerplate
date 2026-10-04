"""A partial update refuses ``null`` for the columns the row requires."""

import pytest
from pydantic import ValidationError
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from src.modules.common.schemas import PartialUpdate, not_nullable_columns


class _Base(DeclarativeBase):
    """A base of its own, so the app's metadata stays untouched."""


class _Widget(_Base):
    __tablename__ = "widgets_for_a_test"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    note: Mapped[str | None]


class _WidgetUpdate(PartialUpdate):
    NOT_NULLABLE = not_nullable_columns(_Widget)

    name: str | None = None
    note: str | None = None


def test_the_required_columns_come_from_the_model():
    assert _WidgetUpdate.NOT_NULLABLE == ("id", "name")


def test_a_required_column_cannot_be_nulled():
    with pytest.raises(ValidationError, match="name"):
        _WidgetUpdate(name=None)


def test_a_nullable_column_still_accepts_null():
    assert _WidgetUpdate(note=None).note is None


def test_omitting_a_field_leaves_it_alone():
    assert _WidgetUpdate().name is None
