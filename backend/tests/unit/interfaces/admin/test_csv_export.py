"""Which cells the admin CSV export writes as text, and which views write them."""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqladmin import ModelView

from src.interfaces.admin.mixins import TextCsvExportMixin, as_spreadsheet_text
from src.wiring.admin import ADMIN_VIEWS

EXPORTING_VIEWS = [view for view in ADMIN_VIEWS if issubclass(view, ModelView) and view.can_export]
"""The registered model views sqladmin serves an export for."""


@pytest.mark.parametrize("cell", ["=1+1", "+1", "-1", "@SUM(A1)", "\tcmd", "\rcmd"])
def test_text_a_spreadsheet_would_run_is_quoted(cell: str):
    assert as_spreadsheet_text(cell) == f"'{cell}"


@pytest.mark.parametrize("cell", ["Ada Lovelace", "ada@example.com", "", "1+1", "'=1+1"])
def test_every_other_string_is_written_as_it_is(cell: str):
    assert as_spreadsheet_text(cell) == cell


@pytest.mark.parametrize(
    "value",
    [-1, 0, 7, -2.5, Decimal("-2.5"), True, False, None, date(2026, 10, 1), datetime(2026, 10, 1, 9, tzinfo=UTC)],
)
def test_a_value_that_is_not_text_is_only_rendered(value: object):
    assert as_spreadsheet_text(value) == str(value)


def test_the_panel_registers_a_view_that_exports():
    """The sweep below says nothing where nothing exports."""
    assert EXPORTING_VIEWS


def provider_of(view: type, name: str) -> type:
    """The class in ``view``'s resolution order that provides ``name``."""
    return next(base for base in view.__mro__ if name in vars(base))


@pytest.mark.parametrize("view", EXPORTING_VIEWS, ids=lambda view: view.__name__)
def test_every_view_that_exports_writes_its_cells_as_text(view: type[ModelView]):
    """sqladmin exports every view unless told not to, and writes each cell as it stands.

    Both export paths have to resolve to the mixin: a view that lists it after ``ModelView``,
    or writes an ``export_data`` of its own, exports what the database holds.
    """
    assert provider_of(view, "export_data") is TextCsvExportMixin
    assert provider_of(view, "custom_export_cell") is TextCsvExportMixin
