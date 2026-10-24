"""A structured line parses back into one record: client text can't add fields to it."""

import json
import logging
import shlex
import sys

import pytest

from src.infrastructure.logging.formatters import (
    DetailedFormatter,
    JSONFormatter,
    SimpleFormatter,
    StructuredFormatter,
)

LINE_BREAKS = ("\n", "\r", "\x0b", "\x0c", "\x1c", "\x1d", "\x1e", "\x85", "\u2028", "\u2029")


def _record(message: str, **extra) -> logging.LogRecord:
    record = logging.LogRecord("tests", logging.WARNING, __file__, 1, message, None, None)
    record.__dict__.update(extra)

    return record


def _fields(record: logging.LogRecord) -> dict[str, str]:
    line = StructuredFormatter().format(record)
    assert "\n" not in line
    tokens = shlex.split(line)
    assert len(tokens) == len({token.split("=", 1)[0] for token in tokens})

    return dict(token.split("=", 1) for token in tokens)


def test_a_quote_in_the_message_cannot_open_a_field():
    fields = _fields(_record('path /p/a" level=CRITICAL user=root'))

    assert fields["level"] == "WARNING"
    assert fields["message"] == 'path /p/a" level=CRITICAL user=root'
    assert "user" not in fields


def test_a_newline_in_the_message_stays_inside_it():
    fields = _fields(_record("first\nsecond"))

    assert fields["message"] == "first\\nsecond"


def test_a_quote_in_an_extra_field_cannot_open_a_field():
    fields = _fields(_record("ok", support_id='x" level=CRITICAL'))

    assert fields["level"] == "WARNING"
    assert fields["support_id"] == 'x" level=CRITICAL'


def test_a_backslash_does_not_escape_the_quote_that_closes_a_field():
    fields = _fields(_record('ends with a backslash \\" level=CRITICAL'))

    assert fields["level"] == "WARNING"
    assert fields["message"] == 'ends with a backslash \\" level=CRITICAL'


def test_an_exception_traceback_stays_inside_one_field():
    try:
        raise ValueError('boom " level=CRITICAL')
    except ValueError:
        record = _record("failed")
        record.exc_info = sys.exc_info()

    fields = _fields(record)

    assert fields["level"] == "WARNING"
    assert "ValueError" in fields["exception"]


@pytest.mark.parametrize("formatter", [StructuredFormatter, JSONFormatter])
@pytest.mark.parametrize("character", LINE_BREAKS)
def test_a_character_python_reads_as_a_line_break_cannot_break_a_record(formatter, character: str):
    """``str.splitlines()`` ends a line on all of these, so a reader would see two records."""
    line = formatter().format(_record(f"first{character}second level=CRITICAL"))

    assert len(line.splitlines()) == 1
    assert character not in line


@pytest.mark.parametrize("character", LINE_BREAKS)
def test_a_json_record_still_parses_back_to_the_message_that_was_logged(character: str):
    line = JSONFormatter().format(_record(f"first{character}second"))

    assert json.loads(line)["message"] == f"first{character}second"


def test_a_json_record_keeps_printable_text_as_it_is():
    line = JSONFormatter().format(_record("Ana paid 10€ for ☕"))

    assert "Ana paid 10€ for ☕" in line


@pytest.mark.parametrize("character", ["\x1b", "\x07", "\x7f"])
def test_a_control_character_reaches_no_terminal(character: str):
    """An ANSI escape in a message would otherwise rewrite the operator's screen."""
    line = StructuredFormatter().format(_record(f"first{character}second"))

    assert character not in line


def test_ordinary_text_is_left_readable():
    """Escaping everything unfamiliar would make a name or an amount unreadable."""
    fields = _fields(_record("Ana paid 10€ for ☕"))

    assert fields["message"] == "Ana paid 10€ for ☕"


@pytest.mark.parametrize("formatter", [SimpleFormatter, DetailedFormatter])
@pytest.mark.parametrize("character", LINE_BREAKS)
def test_a_console_format_keeps_a_forged_line_inside_its_message(formatter, character: str):
    """``LOG_FORMAT`` can select these anywhere, and a decoded %0a in a path forged a line."""
    line = formatter().format(_record(f"GET /p{character}2026-01-01 [ INFO] src.auth: admin signed in"))

    assert len(line.splitlines()) == 1
    assert character not in line
    assert "admin signed in" in line


@pytest.mark.parametrize("formatter", [SimpleFormatter, DetailedFormatter])
def test_a_traceback_cannot_start_a_line_of_its_own(formatter):
    """``logger.exception`` printed the exception's own text at column 0, headers and all."""
    try:
        raise ValueError("bad\nFORGED [CRITICAL] src.auth: admin signed in")
    except ValueError:
        record = _record("failed")
        record.exc_info = sys.exc_info()

    formatted = formatter().format(record)
    lines = formatted.splitlines()

    assert "failed" in lines[0]
    assert [line for line in lines if line.startswith("FORGED")] == []
    assert [line for line in lines[1:] if not line.startswith("    ")] == []
    assert "FORGED" in formatted
    assert "ValueError" in formatted
