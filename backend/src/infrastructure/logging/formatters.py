"""Custom logging formatters for different environments and output types.

This module provides specialized formatters that adapt to different environments
and use cases. Each formatter is optimized for its intended output medium and
provides the appropriate level of detail and structure.

Available Formatters:
- SimpleFormatter: Basic console output for development
- DetailedFormatter: Verbose console output with full context
- StructuredFormatter: Structured logging with key-value pairs
- JSONFormatter: Machine-readable JSON format for production
"""

import json
import logging
import traceback
from datetime import UTC, datetime
from types import TracebackType

_ExcInfo = tuple[type[BaseException], BaseException, TracebackType | None] | tuple[None, None, None]

_WHITESPACE_ESCAPES = {"\n": "\\n", "\r": "\\r", "\t": "\\t"}

_FIELD_ESCAPES = {"\\": "\\\\", '"': '\\"'}

_JSON_UNESCAPED_BREAKS = {"\x85": "\\u0085", "\u2028": "\\u2028", "\u2029": "\\u2029"}


def _printable(value: str) -> str:
    """``value`` on one line, with every character a terminal would act on written out."""
    written = []
    for character in value:
        if character in _WHITESPACE_ESCAPES:
            written.append(_WHITESPACE_ESCAPES[character])
        elif character.isprintable():
            written.append(character)
        else:
            written.append(f"\\u{ord(character):04x}")

    return "".join(written)


def _escaped(value: str) -> str:
    """``value`` as the text of a quoted field, with the quote and the backslash escaped too."""
    return _printable("".join(_FIELD_ESCAPES.get(character, character) for character in value))


def _quoted(value: str) -> str:
    """``value`` as a quoted field, with the characters that would end it escaped."""
    return f'"{_escaped(value)}"'


def _indented(text: str) -> str:
    """``text`` as continuation lines of the record above it, none of them at column 0."""
    return "\n".join(f"    {_printable(line)}" for line in text.splitlines())


class _EscapedMessageFormatter(logging.Formatter):
    """A formatter whose message stays on the line it was written to, its traceback indented."""

    def formatMessage(self, record: logging.LogRecord) -> str:
        record.message = _printable(record.message)

        return super().formatMessage(record)

    def formatException(self, ei: _ExcInfo) -> str:
        return _indented(super().formatException(ei))

    def formatStack(self, stack_info: str) -> str:
        return _indented(super().formatStack(stack_info))


class SimpleFormatter(_EscapedMessageFormatter):
    """Simple formatter for basic console output.

    Provides clean, readable output for development environments
    where human readability is prioritized over structure.

    Format: [LEVEL] module_name: message
    Example: [INFO] app.users.service: User created successfully
    """

    def __init__(self):
        super().__init__(fmt="[%(levelname)s] %(name)s: %(message)s", datefmt="%H:%M:%S")


class DetailedFormatter(_EscapedMessageFormatter):
    """Detailed formatter with timestamp and context information.

    Provides comprehensive information for debugging and development,
    including timestamps, module information, and optional context.

    Format: YYYY-MM-DD HH:MM:SS [LEVEL] module_name: message
    """

    def __init__(self):
        super().__init__(fmt="%(asctime)s [%(levelname)8s] %(name)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S")


class StructuredFormatter(logging.Formatter):
    """Structured formatter with key-value pairs.

    Provides structured logging that's both human-readable and
    machine-parseable. Includes automatic context extraction.

    Format: timestamp level=LEVEL module=name message="text" key1=value1 key2=value2
    """

    def format(self, record: logging.LogRecord) -> str:
        timestamp = datetime.now(UTC).isoformat()
        parts = [
            f"timestamp={timestamp}",
            f"level={record.levelname}",
            f"module={record.name}",
            f"message={_quoted(record.getMessage())}",
        ]

        if hasattr(record, "__dict__"):
            for key, value in record.__dict__.items():
                if key not in [
                    "name",
                    "msg",
                    "args",
                    "levelname",
                    "levelno",
                    "pathname",
                    "filename",
                    "module",
                    "lineno",
                    "funcName",
                    "created",
                    "msecs",
                    "relativeCreated",
                    "thread",
                    "threadName",
                    "processName",
                    "process",
                    "message",
                    "exc_info",
                    "exc_text",
                    "stack_info",
                ]:
                    if isinstance(value, int | float | bool):
                        parts.append(f"{key}={value}")
                    else:
                        parts.append(f"{key}={_quoted(str(value))}")

        if record.exc_info:
            parts.append(f"exception={_quoted(self.formatException(record.exc_info))}")

        return " ".join(parts)


class JSONFormatter(logging.Formatter):
    """JSON formatter for machine-readable structured logging.

    Optimized for production environments where logs are processed
    by log aggregation systems. Provides complete context in JSON format.
    """

    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "module": record.name,
            "message": record.getMessage(),
            "filename": record.filename,
            "function": record.funcName,
            "line_number": record.lineno,
            "thread_id": record.thread,
            "process_id": record.process,
        }

        for key, value in record.__dict__.items():
            if key not in [
                "name",
                "msg",
                "args",
                "levelname",
                "levelno",
                "pathname",
                "filename",
                "module",
                "lineno",
                "funcName",
                "created",
                "msecs",
                "relativeCreated",
                "thread",
                "threadName",
                "processName",
                "process",
                "message",
                "exc_info",
                "exc_text",
                "stack_info",
            ]:
                try:
                    json.dumps(value)
                    log_data[key] = value
                except (TypeError, ValueError):
                    log_data[key] = str(value)

        if record.exc_info:
            log_data["exception"] = {
                "type": record.exc_info[0].__name__ if record.exc_info[0] else None,
                "message": str(record.exc_info[1]) if record.exc_info[1] else None,
                "traceback": traceback.format_exception(*record.exc_info),
            }

        dumped = json.dumps(log_data, ensure_ascii=False)
        for character, escape in _JSON_UNESCAPED_BREAKS.items():
            dumped = dumped.replace(character, escape)

        return dumped


def get_formatter(format_type: str) -> logging.Formatter:
    """Get the appropriate formatter based on format type.

    Args:
        format_type: The type of formatter to create
                    ("simple", "detailed", "structured", "json")

    Returns:
        Configured formatter instance

    Raises:
        ValueError: If format_type is not recognized
    """
    formatters: dict[str, type[logging.Formatter]] = {
        "simple": SimpleFormatter,
        "detailed": DetailedFormatter,
        "structured": StructuredFormatter,
        "json": JSONFormatter,
    }

    formatter_class = formatters.get(format_type.lower())
    if formatter_class is None:
        raise ValueError(f"Unknown format type: {format_type}. Available: {', '.join(formatters.keys())}")

    return formatter_class()
