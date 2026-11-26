"""Every setting has the value it had before settings read the environment at build time.

The tables were written from the blueprint repo, where every feature is selected, so this file
stays in the blueprint.
"""

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from src.infrastructure.config.settings import Settings

HERE = Path(__file__).resolve().parent
ENV_EXAMPLE = HERE.parents[3] / ".env.example"
DEFAULTS = json.loads((HERE / "defaults.json").read_text())
"""Every field's value with nothing set."""
EXAMPLE_VALUES = json.loads((HERE / "example_values.json").read_text())
"""Every field's value with `backend/.env.example` as the environment file and nothing else set."""


def test_the_tables_are_every_field():
    assert sorted(DEFAULTS) == sorted(Settings.model_fields)
    assert sorted(EXAMPLE_VALUES) == sorted(Settings.model_fields)


@pytest.mark.parametrize("name", sorted(DEFAULTS))
def test_every_default_is_the_one_it_was(name: str):
    with patch.dict(os.environ, {}, clear=True):
        assert repr(getattr(Settings(), name)) == DEFAULTS[name]


@pytest.mark.parametrize("name", sorted(EXAMPLE_VALUES))
def test_every_value_the_example_gives_is_the_one_it_gave(name: str):
    with patch.dict(os.environ, {}, clear=True):
        assert repr(getattr(Settings(_env_file=ENV_EXAMPLE), name)) == EXAMPLE_VALUES[name]
