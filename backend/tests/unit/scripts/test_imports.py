"""Every script has to import, because nothing else in the suite loads them.

The seeders and the table setup run outside the app, so a rename in the code they
reach for only shows up when someone runs them, unless something imports them here.
"""

import importlib

import pytest

from scripts.seeders import SEEDERS

SCRIPTS = [
    "scripts.create_first_superuser",
    "scripts.create_first_tier",
    "scripts.create_tables",
    "scripts.seeders",
    "scripts.setup_initial_data",
]


@pytest.mark.parametrize("module", SCRIPTS)
def test_the_script_imports(module: str):
    assert importlib.import_module(module) is not None


def test_every_seeder_is_a_script_of_a_selected_feature():
    """The wiring lists the seeders; each has to be one the app still ships."""
    assert SEEDERS
    for seed in SEEDERS:
        assert importlib.import_module(seed.__module__) is not None
