"""What the test runner is configured with.

``env`` needs pytest-env, which isn't installed, so it warned on every run; and
the value it set, ``ENVIRONMENT=pytest``, is not one the settings accept.
"""

import tomllib
from pathlib import Path

CONFIG = tomllib.loads((Path(__file__).resolve().parents[2] / "pyproject.toml").read_text())["tool"]["pytest"]["ini_options"]


def test_no_environment_is_forced_on_the_suite():
    assert "env" not in CONFIG


def test_warnings_are_shown():
    assert "--disable-warnings" not in CONFIG["addopts"]
