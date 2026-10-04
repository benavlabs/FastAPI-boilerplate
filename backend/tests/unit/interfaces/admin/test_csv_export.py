"""Which cells the admin CSV export writes as text."""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from src.interfaces.admin.mixins import as_spreadsheet_text


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
