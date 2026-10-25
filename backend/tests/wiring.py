"""Fixture modules of the selected features, loaded by ``tests/conftest.py``.

Written by the generator in `tools/removal_drill.py`, which a test compares this file against.
"""

PYTEST_PLUGINS: list[str] = [
    "tests.fixtures.accounts",
    "tests.fixtures.tiers",
]
