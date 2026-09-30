"""``LOG_FORMAT`` decides the format; each environment supplies the default."""

import logging

import pytest

from src.infrastructure.config.enums import LogFormat
from src.infrastructure.config.settings import EnvironmentOption, Settings
from src.infrastructure.logging import config as logging_config
from src.infrastructure.logging.formatters import DetailedFormatter, JSONFormatter, StructuredFormatter


@pytest.fixture
def root_logger():
    """The root logger, with its handlers put back afterwards."""
    root = logging.getLogger()
    original = root.handlers[:]
    root.handlers = []
    yield root
    root.handlers = original


def _formatters(root_logger, monkeypatch, environment: EnvironmentOption, **overrides) -> list[type]:
    settings = Settings(ENVIRONMENT=environment, LOG_CONSOLE_ENABLED=True, LOG_FILE_ENABLED=False, **overrides)
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
