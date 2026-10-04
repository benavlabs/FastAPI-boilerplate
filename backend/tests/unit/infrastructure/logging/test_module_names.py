"""A logger asked for by a module is named after that module.

The name decides per-module levels and fills the ``module`` field of a structured
line, so one shared name makes both useless.
"""

from src.infrastructure.logging import get_logger
from src.infrastructure.logging.factory import get_logger_with_correlation_id
from src.modules.common.utils import error_handler

logger = get_logger()


def test_a_module_level_logger_is_named_after_its_module():
    assert logger.name == __name__


def test_an_explicit_name_is_left_alone():
    assert get_logger("custom.name").name == "custom.name"


def test_the_apps_own_loggers_are_named_after_their_modules():
    assert error_handler.logger.name == "src.modules.common.utils.error_handler"


def test_a_correlation_id_logger_is_named_after_the_module_that_asked():
    """It used to name the factory itself, so every request logged under one name."""
    traced = get_logger_with_correlation_id("req-123456")

    assert traced.logger.name == __name__
    assert traced.extra == {"correlation_id": "req-123456"}
