"""Every script has to import, because nothing else in the suite loads them.

The seeders and the table setup run outside the app, so a rename in the code they
reach for only shows up when someone runs them, unless something imports them here.
"""

import importlib
from pathlib import Path

import pytest

from scripts.seeders import SEEDERS

SCRIPTS = sorted(path.stem for path in (Path(__file__).resolve().parents[3] / "scripts").glob("*.py"))


@pytest.mark.parametrize("script", SCRIPTS)
def test_the_script_imports(script: str):
    assert importlib.import_module(f"scripts.{script}") is not None


def test_every_seeder_is_a_script_this_project_ships():
    """The wiring lists the seeders; each has to be one the app still has."""
    for seed in SEEDERS:
        assert importlib.import_module(seed.__module__) is not None
