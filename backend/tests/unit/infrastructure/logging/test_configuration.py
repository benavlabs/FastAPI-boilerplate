"""``LOG_FORMAT`` decides the console format; each environment supplies the default."""

import logging
import os
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from src.infrastructure.config.enums import LogFormat
from src.infrastructure.config.settings import EnvironmentOption, Settings
from src.infrastructure.logging import config as logging_config
from src.infrastructure.logging.formatters import DetailedFormatter, JSONFormatter, StructuredFormatter


@pytest.fixture
def root_logger():
    """The root logger, with its handlers closed and put back afterwards."""
    root = logging.getLogger()
    original = root.handlers[:]
    root.handlers = []
    yield root
    for handler in root.handlers:
        handler.close()
    root.handlers = original


def _formatters(root_logger, monkeypatch, environment: EnvironmentOption, **overrides) -> list[type]:
    configured = {"LOG_CONSOLE_ENABLED": True, "LOG_FILE_ENABLED": False, **overrides}
    settings = Settings(ENVIRONMENT=environment, **configured)
    monkeypatch.setattr(logging_config, "get_settings", lambda: settings)
    logging_config.setup_logging_configuration()

    return [type(handler.formatter) for handler in root_logger.handlers]


@pytest.mark.parametrize(
    ("environment", "expected"),
    [
        (EnvironmentOption.DEVELOPMENT, DetailedFormatter),
        (EnvironmentOption.STAGING, StructuredFormatter),
        (EnvironmentOption.PRODUCTION, JSONFormatter),
    ],
)
def test_each_environment_has_its_own_default_format(root_logger, monkeypatch, environment, expected):
    assert _formatters(root_logger, monkeypatch, environment) == [expected]


@pytest.mark.parametrize(
    ("chosen", "expected"),
    [
        (LogFormat.JSON.value, JSONFormatter),
        (LogFormat.STRUCTURED.value, StructuredFormatter),
        (LogFormat.DETAILED.value, DetailedFormatter),
    ],
)
def test_the_configured_format_wins(root_logger, monkeypatch, chosen, expected):
    """The docs tell operators to set LOG_FORMAT=json; nothing used to read it."""
    assert _formatters(root_logger, monkeypatch, EnvironmentOption.DEVELOPMENT, LOG_FORMAT=chosen) == [expected]


def test_the_configured_format_leaves_the_file_handler_alone(root_logger, monkeypatch, tmp_path):
    """A file is read by a collector that expects the environment's format, not an operator."""
    formatters = _formatters(
        root_logger,
        monkeypatch,
        EnvironmentOption.PRODUCTION,
        LOG_FORMAT=LogFormat.DETAILED.value,
        LOG_FILE_ENABLED=True,
        LOG_FILE_PATH=str(tmp_path / "app.log"),
    )

    assert formatters == [DetailedFormatter, JSONFormatter]


@pytest.mark.parametrize("chosen", ["xml", "jsonl", "detailedx", "simple detailed"])
def test_a_format_nothing_implements_is_refused(chosen: str):
    with pytest.raises(ValidationError, match="LOG_FORMAT"):
        Settings(LOG_FORMAT=chosen)


@pytest.mark.parametrize("chosen", ["json", "JSON", "Detailed", " structured"])
def test_a_format_is_read_however_it_is_written(chosen: str):
    assert Settings(LOG_FORMAT=chosen).LOG_FORMAT == chosen.strip().lower()


def test_a_format_nothing_implements_is_refused_as_the_settings_load():
    """It used to raise ``ValueError`` from the formatter the first time anything logged."""
    result = subprocess.run(
        [sys.executable, "-c", "import src.infrastructure.config.settings"],
        cwd=Path(__file__).resolve().parents[4],
        capture_output=True,
        text=True,
        env={**os.environ, "LOG_FORMAT": "xml"},
    )

    assert result.returncode != 0
    assert "LOG_FORMAT" in result.stderr
