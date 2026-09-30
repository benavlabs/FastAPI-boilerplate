"""The drill's own manifest: a selection has to pull in everything it needs.

The drill lives outside the backend package, so it is loaded from its path rather
than imported.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

DRILL_PATH = Path(__file__).resolve().parents[3] / "tools" / "removal_drill.py"

_spec = importlib.util.spec_from_file_location("removal_drill", DRILL_PATH)
assert _spec is not None and _spec.loader is not None
drill = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = drill
_spec.loader.exec_module(drill)


def test_a_selection_pulls_in_what_its_features_need_all_the_way_down():
    """tier_limits needs tiers and ratelimit, and both of those need accounts."""
    assert drill._selected_from(("tier_limits",)) == {"tier_limits", "tiers", "ratelimit", "accounts"}


@pytest.mark.parametrize("preset", sorted(drill.PRESETS))
def test_every_preset_is_closed_under_its_requirements(preset: str):
    chosen = drill._selected(preset)

    for feature in chosen:
        assert set(drill.REQUIRES.get(feature, ())) <= chosen, feature


def test_every_feature_the_wiring_knows_is_in_the_manifest():
    """A feature missing here would never be removed by any preset."""
    assert set(drill.FEATURES) >= set(drill.REQUIRES)
    assert set(drill.PRESETS["everything"]) == set(drill.FEATURES)


def test_a_scratch_project_never_carries_the_repository_env_file():
    """It would point a build at whatever the developer runs locally."""
    assert ".env" in drill.COPY_EXCLUDES
