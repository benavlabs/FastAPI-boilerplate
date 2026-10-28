"""The catalog describes this repository, and `tools/removal_drill.py` is what it describes.

`blueprint.toml` is read by fastro, which isn't a dependency here yet, so nothing in this
file imports it: the rules it checks are transcribed from the catalog spec, and the facts it
checks against come from the drill, which is the repository's own account of its features.

This file goes when `fastro blueprint lint` and `fastro blueprint verify` replace the drill.
"""

import ast
import importlib.util
import re
import sys
import tomllib
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]

CATALOG = REPO_ROOT / "blueprint.toml"
BACKEND_PYPROJECT = REPO_ROOT / "backend" / "pyproject.toml"

FEATURE_NAME = re.compile(r"^[a-z][a-z0-9_]*$")
"""Spec 1.2. Written out rather than imported, because fastro is not a dependency yet."""

BLUEPRINT_NAME = re.compile(r"^[a-z][a-z0-9-]*$")

NOT_YET_WRITTEN = {"fastro.toml"}
"""`fastro.toml` is declared in the catalog before it exists."""


def _catalog() -> dict[str, Any]:
    with CATALOG.open("rb") as handle:
        return tomllib.load(handle)


def _drill():
    """The drill's manifest, loaded as a module: its dataclasses need it in ``sys.modules``."""
    spec = importlib.util.spec_from_file_location("removal_drill_manifest", REPO_ROOT / "tools" / "removal_drill.py")
    assert spec is not None and spec.loader is not None
    manifest = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = manifest
    spec.loader.exec_module(manifest)

    return manifest


def test_the_catalog_parses():
    assert _catalog()["blueprint"]["name"] == "fastro"


def test_it_names_itself_the_way_the_spec_allows():
    blueprint = _catalog()["blueprint"]

    assert BLUEPRINT_NAME.match(blueprint["name"])
    assert blueprint["schema"] == 1
    assert blueprint["python_root"] == "backend"
    assert blueprint["import_root"] == "src"


def test_the_version_is_the_one_the_backend_ships():
    """FR002: a release tag is a blueprint release, so the two versions move together."""
    with BACKEND_PYPROJECT.open("rb") as handle:
        backend = tomllib.load(handle)

    assert _catalog()["blueprint"]["version"] == backend["project"]["version"]


def test_development_builds_of_the_tool_can_read_it():
    """Spec 1.6: `0.1.0.dev0` sorts below `0.1`, so the lower bound has to name it."""
    assert _catalog()["blueprint"]["requires_fastro"] == ">=0.1.0.dev0,<0.2"


def test_the_core_dependencies_are_the_ones_the_backend_declares():
    """The catalog carries the backend's lists until they are split per feature."""
    with BACKEND_PYPROJECT.open("rb") as handle:
        backend = tomllib.load(handle)

    dependencies = _catalog()["blueprint"]["dependencies"]

    assert dependencies["runtime"] == backend["project"]["dependencies"]
    assert dependencies["dev"] == backend["project"]["optional-dependencies"]["dev"]


@pytest.mark.parametrize("entry", sorted(_catalog()["blueprint"]["blueprint_only"]))
def test_every_blueprint_only_path_is_written_the_way_the_spec_reads_them(entry: str):
    """Spec 1.1: a trailing slash means the subtree, and without one it is a single file.

    `docs` rather than `docs/` would name one file nobody has, and the whole tree would
    reach projects.
    """
    assert not entry.startswith("/")
    assert ".." not in Path(entry).parts
    assert entry.endswith("/") == (REPO_ROOT / entry).is_dir()


@pytest.mark.parametrize("entry", sorted(set(_catalog()["blueprint"]["blueprint_only"]) - NOT_YET_WRITTEN))
def test_every_blueprint_only_path_is_one_this_repo_has(entry: str):
    """A path that no longer exists keeps a file out of projects that nobody meant to keep out."""
    assert (REPO_ROOT / entry).exists()


def test_the_things_projects_must_not_receive_are_listed():
    """The catalog, the drill, the docs and the tool's own tree belong to the blueprint only."""
    listed = set(_catalog()["blueprint"]["blueprint_only"])

    assert {"blueprint/", "blueprint.toml", "fastro.toml", "docs/", "tools/", "cli/"} <= listed
    assert "backend/tests/unit/test_blueprint_catalog.py" in listed


def test_the_docs_reading_tests_stay_in_the_blueprint():
    """They read `docs/`, which projects don't get, so they would fail in one."""
    listed = set(_catalog()["blueprint"]["blueprint_only"])

    for name in ("test_docs_imports", "test_docs_recipes", "test_docs_scripts", "test_docs_wiring", "test_image_contents"):
        assert f"backend/tests/unit/{name}.py" in listed


def test_the_verify_sets_are_the_drills_presets():
    """`everything` is implied by the spec, so the named sets are the other eight."""
    expected = {name: list(features) for name, features in _drill().PRESETS.items() if name != "everything"}

    assert _catalog()["verify"]["sets"] == expected


def test_every_preset_is_closed_under_what_its_features_require():
    """A preset that names tier_limits without tiers would generate a project that can't import."""
    requires = _drill().REQUIRES

    for name, features in _catalog()["presets"].items():
        for feature in features:
            assert set(requires.get(feature, ())) <= set(features), f"{name} is missing what {feature} requires"


def test_the_presets_name_features_this_repository_has():
    known = set(_drill().FEATURES)

    for name, features in _catalog()["presets"].items():
        assert set(features) <= known, name
        for feature in features:
            assert FEATURE_NAME.match(feature)


def test_full_is_every_feature():
    assert sorted(_catalog()["presets"]["full"]) == sorted(_drill().FEATURES)


ONE_OF_EACH = {"root_routers", "docs_guard", "email_sender", "cache_decorator"}
"""The points a project may fill once: each renders as a single value with a fallback."""


def _ref(text: str) -> tuple[str, str, str]:
    """A spec 1.4 ref, as (module, attribute, local name)."""
    body, _, alias = text.partition(" as ")
    module, _, attribute = body.partition(":")

    return module, attribute, alias or attribute


def _binding(entry: str) -> tuple[str, str, str]:
    """What a wiring file under ``src/wiring/`` binds for this ref: (module, attribute, name).

    Spec 2.8: a file under the import root imports relatively, so ``src.a.b:name`` is read
    from ``..a.b``.
    """
    module, attribute, alias = _ref(entry)

    return ".." + module.removeprefix("src."), attribute, alias


def _bindings(source: str) -> set[tuple[str, str, str]]:
    """Every (module, attribute, local name) the imports in ``source`` bind.

    Read with ``ast`` rather than by matching text: the drill merges names from one module
    into a single statement and wraps long ones over several lines, and neither shape
    contains the single-name line a substring check would look for.
    """
    bindings: set[tuple[str, str, str]] = set()
    for node in ast.parse(source).body:
        if isinstance(node, ast.ImportFrom):
            module = "." * node.level + (node.module or "")
            bindings.update((module, alias.name, alias.asname or alias.name) for alias in node.names)

    return bindings


def _defines(module: str, attribute: str) -> bool:
    """Whether ``module`` defines ``attribute`` at its top level, read without importing."""
    path = REPO_ROOT / "backend" / Path(*module.split(".")).with_suffix(".py")
    if not path.exists():
        return False

    tree = ast.parse(path.read_text())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == attribute for target in node.targets
        ):
            return True
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == attribute:
            return True
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef) and node.name == attribute:
            return True
        if isinstance(node, ast.ImportFrom | ast.Import) and any(
            (alias.asname or alias.name) == attribute for alias in node.names
        ):
            return True

    return False


@pytest.mark.parametrize("name", sorted(_catalog()["points"]))
def test_every_point_is_declared_the_way_the_spec_asks(name: str):
    """Spec 2.3: a cardinality, and one line saying what the point collects."""
    point = _catalog()["points"][name]

    assert FEATURE_NAME.match(name)
    assert point["cardinality"] in {"many", "one"}
    assert point["doc"].strip() == point["doc"]
    assert "\n" not in point["doc"]


def test_the_points_a_project_may_fill_once_are_the_ones_rendered_as_a_value():
    """A second contribution to one of these is an error, so the set has to be exact."""
    points = _catalog()["points"]
    single = {name for name, point in points.items() if point["cardinality"] == "one"}

    assert single == ONE_OF_EACH


def test_the_database_checks_belong_to_no_feature():
    """The drill wires them whatever is selected, so the catalog gives them to core."""
    core = _catalog()["core"]["contributes"]["critical_readiness"]
    with_nothing_selected = _drill()._wiring_hooks(set())
    rendered = with_nothing_selected.split("CRITICAL_READINESS_CHECKS: tuple[ReadinessCheck, ...] = (")[1]

    assert [_ref(entry)[2] for entry in core] == [name.strip() for name in rendered.split(")")[0].split(",") if name.strip()]


@pytest.mark.parametrize("entry", _catalog()["core"]["contributes"]["critical_readiness"])
def test_every_core_contribution_is_imported_the_way_the_drill_imports_it(entry: str):
    """The names alone would accept a ref that kept the alias and changed the module."""
    assert _binding(entry) in _bindings(_drill()._wiring_hooks(set()))


@pytest.mark.parametrize("entry", _catalog()["core"]["contributes"]["critical_readiness"])
def test_every_core_contribution_names_something_that_exists(entry: str):
    """Spec 1.4: the attribute has to be defined at the module's top level."""
    module, attribute, _ = _ref(entry)

    assert _defines(module, attribute), entry


def test_the_import_reader_sees_a_name_the_drill_merges():
    """Two names from one module become one statement, whose second name no line contains."""
    bindings = _bindings(_drill()._wiring_hooks({"accounts"}))

    assert ("..infrastructure.auth.health", "limiter_readiness", "limiter_readiness") in bindings
    assert ("..infrastructure.auth.health", "sessions_readiness", "sessions_readiness") in bindings


def test_the_import_reader_sees_a_name_the_drill_wraps():
    """The composition import is written over several lines, so no single line holds it."""
    bindings = _bindings(_drill()._wiring_hooks(set()))

    assert ("..infrastructure.composition", "ReadinessCheck", "ReadinessCheck") in bindings
