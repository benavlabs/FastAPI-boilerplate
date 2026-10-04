"""The drill's own manifest: a selection has to pull in everything it needs.

The drill lives outside the backend package, so it is loaded from its path rather
than imported.
"""

import ast
import importlib.util
import shutil
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


class TestReportingACheck:
    """A failing preset has to say what failed: the drill is the only place that output exists."""

    def test_a_failing_check_prints_what_it_printed(self):
        failed = drill.Result(
            "tests",
            False,
            "1 failed, 664 passed",
            "FAILED tests/integration/test_x.py::test_y - assert 2 == 1\n1 failed, 664 passed",
        )

        report = drill._report(failed)

        assert "FAIL" in report
        assert "tests/integration/test_x.py::test_y" in report

    def test_a_long_failure_prints_its_end_and_says_what_it_dropped(self):
        """A ``-q`` run is mostly progress dots; the failure sits at the end of it."""
        printed = "\n".join(f"line {number}" for number in range(100))

        report = drill._report(drill.Result("tests", False, "line 99", printed))

        assert "line 99" in report
        assert "line 0" not in report
        assert "60 earlier lines" in report

    def test_a_build_that_raises_leaves_its_scratch_copy_behind(self, monkeypatch, capsys):
        """Whatever the build tripped over is only visible in the copy it got to."""

        def failing_build(preset: str, scratch: Path) -> Path:
            raise RuntimeError("copy failed")

        monkeypatch.setattr(drill, "build", failing_build)
        monkeypatch.setattr(sys, "argv", ["removal_drill.py", "core-only"])

        with pytest.raises(RuntimeError, match="copy failed"):
            drill.main()

        printed = capsys.readouterr().out

        assert "scratch copies left in" in printed

        left = Path(printed.split("scratch copies left in ")[1].strip())

        assert left.exists()
        shutil.rmtree(left, ignore_errors=True)

    def test_a_passing_check_prints_its_last_line_only(self):
        passed = drill.Result("tests", True, "665 passed", "a long run of dots\n665 passed")

        report = drill._report(passed)

        assert report.strip() == "PASS  tests        665 passed"


def test_a_scratch_project_never_carries_the_repository_env_file():
    """It would point a build at whatever the developer runs locally."""
    assert ".env" in drill.COPY_EXCLUDES


BACKEND_ROOT = Path(__file__).resolve().parents[2]
GENERATED_FILES = (
    ("src/wiring/settings.py", "_wiring_settings"),
    ("src/wiring/app.py", "_wiring_app"),
    ("src/wiring/hooks.py", "_wiring_hooks"),
    ("src/wiring/models.py", "_wiring_models"),
    ("src/wiring/admin.py", "_wiring_admin"),
    ("scripts/seeders.py", "_seeders"),
    ("tests/wiring.py", "_tests_wiring"),
)


def _without_formatting(source: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """A module's imports and statements, as trees: no docstring, no comments, no layout."""
    body = ast.parse(source).body
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
        body = body[1:]

    imports = sorted(ast.dump(node) for node in body if isinstance(node, ast.Import | ast.ImportFrom))
    statements = [ast.dump(node) for node in body if not isinstance(node, ast.Import | ast.ImportFrom)]

    return tuple(imports), tuple(statements)


def _features_on_disk() -> set[str]:
    """The features this project still carries, read from the source paths they own."""
    repository = BACKEND_ROOT.parent
    present = set()
    for name, feature in drill.FEATURES.items():
        sources = [path for path in feature.paths if path.startswith("backend/src")]
        if sources and all((repository / path).exists() for path in sources):
            present.add(name)

    return present


def test_the_generator_rebuilds_what_this_project_committed():
    """The drill proves a regenerated project reproduces this one, which needs them equal."""
    present = _features_on_disk()

    assert (BACKEND_ROOT / "src/wiring/admin.py").exists() == ("admin" in present)

    for name, generator in GENERATED_FILES:
        committed = BACKEND_ROOT / name
        if name == "src/wiring/admin.py" and "admin" not in present:
            continue

        assert _without_formatting(getattr(drill, generator)(present)) == _without_formatting(committed.read_text()), name
