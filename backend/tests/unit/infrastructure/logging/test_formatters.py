"""A structured line parses back into one record: client text can't add fields to it."""

import logging
import shlex
import sys

from src.infrastructure.logging.formatters import StructuredFormatter


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
