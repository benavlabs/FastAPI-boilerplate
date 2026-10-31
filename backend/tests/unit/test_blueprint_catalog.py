"""The catalog describes this repository, and `tools/removal_drill.py` is what it describes.

`blueprint.toml` is read by fastro, which isn't a dependency here yet, so nothing in this
file imports it: the rules it checks are transcribed from the catalog spec, and the facts it
checks against come from the drill, which is the repository's own account of its features.

This file goes when `fastro blueprint lint` and `fastro blueprint verify` replace the drill.
"""

import ast
import functools
import importlib
import importlib.util
import inspect
import ipaddress
import itertools
import keyword
import re
import sys
import tomllib
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]

CATALOG = REPO_ROOT / "blueprint.toml"
BACKEND_PYPROJECT = REPO_ROOT / "backend" / "pyproject.toml"

FEATURE_NAME = re.compile(r"^[a-z][a-z0-9_]*$")
"""Spec 1.2. Written out rather than imported, because fastro is not a dependency yet."""

BLUEPRINT_NAME = re.compile(r"^[a-z][a-z0-9-]*$")

SET_NAME = re.compile(r"^[a-z][a-z0-9_-]*$")
"""Spec 1.2. A preset or a verify set may carry a hyphen, which a feature name may not."""


@functools.cache
def _catalog() -> dict[str, Any]:
    with CATALOG.open("rb") as handle:
        return tomllib.load(handle)


@functools.cache
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


@pytest.mark.parametrize("entry", sorted(_catalog()["blueprint"]["blueprint_only"]))
def test_every_blueprint_only_path_is_one_this_repo_has(entry: str):
    """A path that no longer exists keeps a file out of projects that nobody meant to keep out."""
    assert (REPO_ROOT / entry).exists()


def _withheld(path: str) -> bool:
    """Whether `blueprint_only` keeps a project from receiving this path (spec 1.1 subtrees)."""
    return any(
        path == entry.rstrip("/") or (entry.endswith("/") and path.startswith(entry))
        for entry in _catalog()["blueprint"]["blueprint_only"]
    )


def _workspace_members() -> list[str]:
    with (REPO_ROOT / "pyproject.toml").open("rb") as handle:
        return list(tomllib.load(handle)["tool"]["uv"]["workspace"]["members"])


def _hook_paths() -> list[str]:
    """The literal head of each pre-commit `files:` pattern, which is a path in the repository."""
    patterns = re.findall(r"^\s*files: (\S+)$", (REPO_ROOT / ".pre-commit-config.yaml").read_text(), re.M)

    return [re.split(r"[(\[{|?*+.\\]", pattern.removeprefix("^"))[0].rstrip("/") for pattern in patterns]


def _readme_references() -> list[str]:
    """The files the README's own markup points at, leaving out what it fetches over the network."""
    found = re.findall(r'src(?:set)?="([^"]+)"', (REPO_ROOT / "README.md").read_text())

    return [reference for reference in found if not reference.startswith("http")]


POINTS_AT = {
    "pyproject.toml": _workspace_members,
    ".pre-commit-config.yaml": _hook_paths,
    "README.md": _readme_references,
}
"""Each root file that names paths, read the way that file spells them."""


@pytest.mark.parametrize("path", sorted(POINTS_AT))
def test_no_file_a_project_receives_points_at_one_it_does_not(path: str):
    """Either the pointer goes or the file does.

    A workspace member a project never receives is a project `uv sync` refuses; a lint pattern
    is a hook over nothing; an image is a hole where the cover was. The three root files are
    the blueprint's own, so they are the ones that go.
    """
    withheld = sorted(target for target in POINTS_AT[path]() if _withheld(target))

    assert not withheld or _withheld(path), (path, withheld)


WITHHELD_POINTERS = {
    "pyproject.toml": "cli",
    ".pre-commit-config.yaml": "cli/src",
    "README.md": "docs/assets",
}
"""What keeps each of the three out of a project, pinned so a reader of it can't go quiet."""


@pytest.mark.parametrize("path", sorted(POINTS_AT))
def test_each_file_still_names_the_path_that_keeps_it_out(path: str):
    """The reason each file is blueprint-only, rather than the fact of it.

    A format that moved on -- a renamed pre-commit key, an image moved out of `docs/` -- would
    leave the rule above with nothing to object to, and the file would ship. When `cli/` goes
    in B3, this is where the question of shipping the workspace root comes back.
    """
    pointed = POINTS_AT[path]()

    assert any(target.startswith(WITHHELD_POINTERS[path]) for target in pointed), pointed


def _literals(module: Path) -> set[str]:
    """Every string literal in a module, less the docstrings, which talk about files rather than
    reach for them."""
    tree = ast.parse(module.read_text())
    docstrings = {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef)
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
    }

    return {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings
    }


def test_no_test_a_project_receives_names_a_tree_it_does_not_get():
    """A test that reaches for `docs/`, `tools/` or `cli/` is a test no project can run.

    `test_removal_drill.py` loads `tools/removal_drill.py`, and `test_baseline.py` read the
    migrations guide: both are files a project never receives, and the drill hid it by copying
    the whole repository into every project it built. Only the subtree entries are compared,
    because a root file's name is ambiguous: a shipped test naming `pyproject.toml` means
    the one under `backend/`.
    """
    trees = [entry for entry in _catalog()["blueprint"]["blueprint_only"] if entry.endswith("/")]
    reaching = {}
    for module in sorted((REPO_ROOT / "backend" / "tests").rglob("*.py")):
        relative = module.relative_to(REPO_ROOT).as_posix()
        if _withheld(relative):
            continue

        named = sorted(
            text for text in _literals(module) for tree in trees if text == tree.rstrip("/") or text.startswith(tree)
        )
        if named:
            reaching[relative] = named

    assert reaching == {}


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
    """`everything` is implied by the spec, and declaring it is an error, so the sets are the other eight."""
    expected = {name: list(features) for name, features in _drill().PRESETS.items() if name != "everything"}
    sets = _catalog()["verify"]["sets"]

    assert "everything" not in sets
    assert sets == expected


@pytest.mark.parametrize("name", sorted(_catalog()["presets"]) + sorted(_catalog()["verify"]["sets"]))
def test_every_preset_and_verify_set_is_named_the_way_the_spec_allows(name: str):
    """Spec 1.2: a name here is lower case and may carry a hyphen, so `accounts-only` reads as one."""
    assert SET_NAME.match(name)


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
    from ``..a.b``. Anything outside it, such as ``scripts.seed``, is imported as written.
    """
    module, attribute, alias = _ref(entry)
    if module.startswith("src."):
        module = ".." + module.removeprefix("src.")

    return module, attribute, alias


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


GENERATED_BY_WIRING = "backend/src/wiring/admin.py"
"""The drill deletes it with the admin feature; the catalog's `[[wiring]]` entry omits it instead."""


def _declared(feature: dict[str, Any]) -> list[tuple[str, str | None]]:
    """A feature's declared paths, each with the condition it is kept under, if any."""
    paths: list[tuple[str, str | None]] = [(path.rstrip("/"), None) for path in feature.get("paths", ())]
    for block in feature.get("when", ()):
        paths.extend((path.rstrip("/"), block["if"]) for path in block.get("paths", ()))

    return paths


def _kept_by_the_catalog(features: dict[str, Any], chosen: set[str]) -> set[str]:
    return {
        path
        for name, feature in features.items()
        if name in chosen
        for path, condition in _declared(feature)
        if condition is None or condition in chosen
    }


def _kept_by_the_drill(manifest: Any, chosen: set[str]) -> set[str]:
    """What `build` leaves on disk: a combination path needs both of its features."""
    kept: set[str] = set()
    for name, feature in manifest.FEATURES.items():
        if name not in chosen:
            continue

        kept.update(path for path in feature.paths if path != GENERATED_BY_WIRING)
        for partner, paths in feature.combination_paths.items():
            if partner in chosen:
                kept.update(paths)

    return kept


def _selections(manifest: Any) -> list[set[str]]:
    """Every selection a project could carry: each subset of the features, closed under requires."""
    closed = []
    for size in range(len(manifest.FEATURES) + 1):
        for combination in itertools.combinations(manifest.FEATURES, size):
            selection = manifest._selected_from(combination)
            if selection not in closed:
                closed.append(selection)

    return closed


def test_the_features_are_the_ones_the_drill_knows():
    """In the drill's order: spec 6.2 hands templates the selection in catalog order."""
    assert list(_catalog()["features"]) == list(_drill().FEATURES)


@pytest.mark.parametrize("name", sorted(_catalog()["features"]))
def test_every_feature_is_declared_the_way_the_spec_asks(name: str):
    """Spec 2.4: a one-line summary, and the heading the checklist groups it under."""
    feature = _catalog()["features"][name]

    assert FEATURE_NAME.match(name)
    assert feature["summary"].strip() == feature["summary"]
    assert "\n" not in feature["summary"]
    assert feature["group"] in {"Accounts", "Operations"}


def test_every_feature_requires_what_the_drill_says_it_requires():
    """A requires that drifts would generate a project whose imports have nothing to bind."""
    requires = _drill().REQUIRES

    for name, feature in _catalog()["features"].items():
        assert list(feature.get("requires", ())) == list(requires.get(name, ()))


@pytest.mark.parametrize(
    ("name", "condition"),
    sorted((name, block["if"]) for name, feature in _catalog()["features"].items() for block in feature.get("when", ())),
)
def test_every_condition_names_a_feature_this_repository_has(name: str, condition: str):
    """Spec 1.3: an unknown name is an error rather than something that reads as false."""
    assert condition in _drill().FEATURES
    assert condition != name


@pytest.mark.parametrize(
    "entry",
    sorted(
        {path for feature in _catalog()["features"].values() for path, _ in _declared(feature)},
    ),
)
def test_every_feature_path_is_one_this_repo_has(entry: str):
    """A path that no longer exists leaves a file in projects that nobody meant to keep."""
    assert not entry.startswith("/")
    assert ".." not in Path(entry).parts
    assert (REPO_ROOT / entry).exists()


@pytest.mark.parametrize("name", sorted(_catalog()["features"]))
def test_a_directory_is_spelled_as_a_subtree_and_a_file_is_not(name: str):
    """Spec 1.1: `src/modules/user` without the slash would name one file nobody has."""
    for path in _catalog()["features"][name].get("paths", ()):
        assert path.endswith("/") == (REPO_ROOT / path).is_dir(), path

    for block in _catalog()["features"][name].get("when", ()):
        for path in block.get("paths", ()):
            assert path.endswith("/") == (REPO_ROOT / path).is_dir(), path


def test_no_path_is_declared_twice():
    """Spec 1.1: two declarations of the identical path are 'owned twice'."""
    declared = [path for feature in _catalog()["features"].values() for path, _ in _declared(feature)]

    assert sorted(declared) == sorted(set(declared))


def test_the_generated_wiring_file_belongs_to_no_feature():
    """It is written by `[[wiring]]`, which leaves it out of a project rather than deleting it."""
    declared = {path for feature in _catalog()["features"].values() for path, _ in _declared(feature)}

    assert GENERATED_BY_WIRING in _drill().FEATURES["admin"].paths
    assert GENERATED_BY_WIRING not in declared


def test_every_selection_keeps_the_files_the_drill_keeps():
    """The catalog gives a shared file to the feature whose subtree holds it, and the drill to both.

    `src/modules/user/admin.py` is admin's work inside accounts' package, and the drill lists it
    under both. One declaration owns it here, so what's compared is the file surviving a
    selection, not which feature spoke for it.
    """
    manifest = _drill()
    features = _catalog()["features"]

    for chosen in _selections(manifest):
        assert _kept_by_the_catalog(features, chosen) == _kept_by_the_drill(manifest, chosen), sorted(chosen)


POINTS: dict[str, tuple[str, str]] = {
    "routers": ("_wiring_app", "ROUTER_MOUNTS"),
    "root_routers": ("_wiring_app", "ROOT_ROUTERS"),
    "api_throttle": ("_wiring_app", "API_THROTTLE"),
    "lifecycles": ("_wiring_app", "LIFECYCLES"),
    "installers": ("_wiring_app", "INSTALLERS"),
    "docs_guard": ("_wiring_app", "DOCS_GUARD"),
    "settings": ("_wiring_settings", "Settings"),
    "permission_sources": ("_wiring_hooks", "PERMISSION_SOURCES"),
    "rate_limit_resolvers": ("_wiring_hooks", "RATE_LIMIT_RESOLVERS"),
    "tier_delete_guards": ("_wiring_hooks", "TIER_DELETE_GUARDS"),
    "tier_delete_releases": ("_wiring_hooks", "TIER_DELETE_RELEASES"),
    "critical_readiness": ("_wiring_hooks", "CRITICAL_READINESS_CHECKS"),
    "informational_readiness": ("_wiring_hooks", "INFORMATIONAL_READINESS_CHECKS"),
    "user_model": ("_wiring_models", "UserModelExtensions"),
    "user_schema": ("_wiring_models", "UserSchemaExtensions"),
    "admin_views": ("_wiring_admin", "ADMIN_VIEWS"),
    "email_sender": ("_wiring_email", "EMAIL_SENDER"),
    "cache_decorator": ("_wiring_cache", "cached"),
    "task_modules": ("_wiring_tasks", "TASK_MODULES"),
    "table_modules": ("_wiring_tables", "TABLE_MODULES"),
    "extra_transports": ("_wiring_transports", "EXTRA_TRANSPORTS"),
    "seeders": ("_seeders", "SEEDERS"),
    "test_plugins": ("_tests_wiring", "PYTEST_PLUGINS"),
}
"""Where the drill writes each point: the generator, and the name it assigns or defines."""


def _slot_of(point: str) -> dict[str, Any]:
    """The one slot that collects this point, which `[[wiring]]` declares exactly once."""
    slots: list[dict[str, Any]] = [
        slot for entry in _catalog()["wiring"] for slot in entry["slots"] if slot.get("point") == point
    ]
    assert len(slots) == 1, point

    return slots[0]


def _fallback_of(point: str) -> str | None:
    """How a point renders with nothing contributed: an expression, or a ref's local name."""
    slot = _slot_of(point)
    fallback = slot.get("fallback")
    if fallback is None:
        return None

    return _ref(fallback)[2] if slot["kind"] in {"class", "reexport"} else fallback


def _appended_to(point: str) -> list[str]:
    """The bases a `class` slot always adds last, by the name they are bound under."""
    return [_ref(ref)[2] for ref in _slot_of(point).get("append", ())]


def _true(condition: str, chosen: set[str]) -> bool:
    """Whether a spec 1.3 condition holds for this selection."""
    tokens = re.findall(r"\(|\)|[^\s()]+", condition)
    position = 0

    def expression() -> bool:
        value = conjunction()
        nonlocal position
        while position < len(tokens) and tokens[position] == "or":
            position += 1
            value = conjunction() or value

        return value

    def conjunction() -> bool:
        value = negation()
        nonlocal position
        while position < len(tokens) and tokens[position] == "and":
            position += 1
            value = negation() and value

        return value

    def negation() -> bool:
        nonlocal position
        if tokens[position] == "not":
            position += 1

            return not negation()

        return atom()

    def atom() -> bool:
        nonlocal position
        token = tokens[position]
        position += 1
        if token == "(":
            value = expression()
            assert tokens[position] == ")", condition
            position += 1

            return value

        if "=" in token:
            raise NotImplementedError(f"{token!r} names an option; this test only selects features.")

        return token in chosen

    held = expression()
    assert position == len(tokens), condition

    return held


def _tables(entries: Any) -> list[dict[str, Any]]:
    """Spec 1.5: a contribution is a bare ref or a table, and reads the same either way."""
    return [{"ref": entry} if isinstance(entry, str) else dict(entry) for entry in entries]


def _contributed(catalog: dict[str, Any], point: str, chosen: set[str]) -> list[dict[str, Any]]:
    """What reaches a point for this selection, in the order spec 2.7 sorts it."""
    collected = [(index, -1, 0, table) for index, table in enumerate(_tables(catalog["core"]["contributes"].get(point, ())))]

    for index, (name, feature) in enumerate(catalog["features"].items()):
        if name not in chosen:
            continue

        entries = list(feature.get("contributes", {}).get(point, ()))
        for block in feature.get("when", ()):
            if _true(block["if"], chosen):
                entries.extend(block.get("contributes", {}).get(point, ()))

        for position, table in enumerate(_tables(entries)):
            if "if" in table and not _true(table["if"], chosen):
                continue

            collected.append((table.get("order", (index + 1) * 100 + position), index, position, table))

    return [table for *_, table in sorted(collected, key=lambda entry: entry[:3])]


def _named(entry: dict[str, Any]) -> Any:
    """The local name a contribution binds, or the literal it contributes."""
    if "value" in entry:
        return entry["value"]

    return _ref(entry["ref"])[2]


def _defined(source: str, name: str) -> ast.AST | None:
    """The value assigned to ``name``, or the class defined under it."""
    for node in ast.parse(source).body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == name:
            return node.value
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
            return node.value
        if isinstance(node, ast.ClassDef) and node.name == name:
            return node

    return None


def _leading_name(element: ast.AST) -> Any:
    """What a rendered item is built around: ``RouterMount(users_router, …)`` is ``users_router``."""
    if isinstance(element, ast.Constant):
        return element.value
    if isinstance(element, ast.Name):
        return element.id
    if isinstance(element, ast.Call):
        return _leading_name(element.args[0]) if element.args else _leading_name(element.func)

    raise AssertionError(ast.unparse(element))


def _rendered(source: str, point: str, name: str) -> list[Any]:
    """The names the drill rendered into this point, in the order it wrote them."""
    if _slot_of(point)["kind"] == "reexport":
        fallback, _, _ = _binding(_slot_of(point)["fallback"])
        bound = [module for module, _, alias in _bindings(source) if alias == name]

        return [] if bound == [fallback] else [name]

    defined = _defined(source, name)
    assert defined is not None, name

    if isinstance(defined, ast.ClassDef):
        bases = [base.id for base in defined.bases if isinstance(base, ast.Name)]
        appended = _appended_to(point)
        if appended:
            assert bases[-len(appended) :] == appended, bases
            bases = bases[: -len(appended)]

        return [] if bases == [_fallback_of(point)] else bases

    if isinstance(defined, ast.Tuple | ast.List):
        return [_leading_name(element) for element in defined.elts]

    return [] if ast.unparse(defined) == _fallback_of(point) else [_leading_name(defined)]


def _written_for(manifest: Any, generator: str, chosen: set[str]) -> str:
    written: str = getattr(manifest, generator)(chosen)

    return written


def _constant(node: ast.expr) -> Any:
    """The value of a rendered literal, such as a mount's prefix or its throttle flag."""
    assert isinstance(node, ast.Constant), ast.unparse(node)

    return node.value


def test_every_declared_point_is_one_the_drill_writes_somewhere():
    """A point missing from this table would skip the comparison below without saying so."""
    assert set(POINTS) == set(_catalog()["points"])


@pytest.mark.parametrize("point", sorted(POINTS))
def test_every_point_is_written_by_a_generator_the_drill_has(point: str):
    generator, _ = POINTS[point]

    assert hasattr(_drill(), generator)


def test_every_declared_point_is_contributed_to_or_filled_by_core():
    """A point no feature and no core contribution reaches would render empty for every project."""
    catalog = _catalog()
    reached = set(catalog["core"]["contributes"])
    for feature in catalog["features"].values():
        reached.update(feature.get("contributes", {}))
        for block in feature.get("when", ()):
            reached.update(block.get("contributes", {}))

    assert set(catalog["points"]) == reached


def test_every_contribution_names_something_that_exists():
    """Spec 1.4: a ref's attribute has to be defined at the top level of its module."""
    catalog = _catalog()
    everything = set(catalog["features"])

    for point in catalog["points"]:
        for entry in _contributed(catalog, point, everything):
            if "value" in entry:
                continue

            module, attribute, _ = _ref(entry["ref"])
            assert _defines(module, attribute), entry


def test_a_point_a_project_fills_once_never_receives_two_contributions():
    """Spec 2.6: a second contribution to a `value` slot is an error rather than a last-wins."""
    catalog = _catalog()
    single = {name for name, point in catalog["points"].items() if point["cardinality"] == "one"}

    for chosen in _selections(_drill()):
        for point in single:
            assert len(_contributed(catalog, point, chosen)) <= 1, (point, sorted(chosen))


@pytest.mark.parametrize("point", sorted(POINTS))
def test_the_catalog_says_what_the_drill_renders(point: str):
    """For every selection a project could carry, what reaches a point is what the drill wrote.

    All 164 of them, not the verify sets: a set builds and tests a project, so the sets are
    few, and a generator is a function of the selection alone, so it costs nothing to ask it
    about combinations no set builds.
    """
    catalog = _catalog()
    manifest = _drill()
    generator, name = POINTS[point]

    for chosen in _selections(manifest):
        expected = [_named(entry) for entry in _contributed(catalog, point, chosen)]
        if generator == "_wiring_admin" and "admin" not in chosen:
            assert expected == [], sorted(chosen)
            continue

        assert _rendered(_written_for(manifest, generator, chosen), point, name) == expected, sorted(chosen)


def test_every_mounted_router_is_mounted_where_the_drill_mounts_it():
    """The prefix and the throttle are the catalog's to carry now, so they are compared too."""
    catalog = _catalog()
    manifest = _drill()

    for chosen in _selections(manifest):
        declared = [(_named(entry), entry["prefix"], entry["throttled"]) for entry in _contributed(catalog, "routers", chosen)]
        mounts = _defined(_written_for(manifest, "_wiring_app", chosen), "ROUTER_MOUNTS")
        assert isinstance(mounts, ast.Tuple)

        rendered = [
            (
                _leading_name(element.args[0]),
                _constant(element.args[1]),
                next(_constant(word.value) for word in element.keywords if word.arg == "throttled"),
            )
            for element in mounts.elts
            if isinstance(element, ast.Call)
        ]

        assert rendered == declared, sorted(chosen)


def test_every_contribution_is_imported_the_way_the_drill_imports_it():
    """A ref that kept the local name and changed the module would render the same line."""
    catalog = _catalog()
    manifest = _drill()
    everything = set(manifest.FEATURES)

    for point, (generator, _) in POINTS.items():
        source = _written_for(manifest, generator, everything)
        bound = _bindings(source)
        for entry in _contributed(catalog, point, everything):
            if "value" in entry:
                continue

            assert _binding(entry["ref"]) in bound, (point, entry)


def test_a_transport_that_is_constructed_says_so():
    """Spec 1.5: `call` is what renders `APIKeyTransport()` rather than the class itself."""
    catalog = _catalog()
    everything = set(catalog["features"])
    entry = _contributed(catalog, "extra_transports", everything)[0]
    rendered = _defined(_written_for(_drill(), "_wiring_transports", everything), "EXTRA_TRANSPORTS")

    assert entry["call"] is True
    assert isinstance(rendered, ast.Tuple) and isinstance(rendered.elts[0], ast.Call)


@pytest.mark.parametrize(
    "condition",
    sorted(
        {block["if"] for feature in _catalog()["features"].values() for block in feature.get("when", ())}
        | {
            entry["if"]
            for feature in _catalog()["features"].values()
            for entries in feature.get("contributes", {}).values()
            for entry in _tables(entries)
            if "if" in entry
        }
    ),
)
def test_every_condition_is_one_this_test_can_evaluate(condition: str):
    """An option atom would need a selection to carry option values, which this test doesn't."""
    assert _true(condition, set(_catalog()["features"])) in {True, False}


@pytest.mark.parametrize(
    ("feature", "option"),
    sorted((name, option) for name, feature in _catalog()["features"].items() for option in feature.get("options", {})),
)
def test_every_option_is_declared_the_way_the_spec_asks(feature: str, option: str):
    """Spec 2.5: named choices, listed once, with the default among them."""
    declared = _catalog()["features"][feature]["options"][option]

    assert FEATURE_NAME.match(option)
    assert declared["choices"] == sorted(set(declared["choices"]), key=declared["choices"].index)
    assert all(choice and not re.search(r"[\s()=]", choice) for choice in declared["choices"])
    assert declared["default"] in declared["choices"]
    assert all(re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", name) for name in declared.get("env", {}))


EXTRA_SERVICES = {
    ("cache", "backend"): {"memcached": ["memcached"]},
    ("taskiq", "broker"): {"rabbitmq": ["rabbitmq"]},
}
"""The service each choice needs on top of what a project already runs, which is redis."""


@pytest.mark.parametrize(("feature", "option"), sorted(EXTRA_SERVICES))
def test_every_extra_service_an_option_asks_for_belongs_to_one_of_its_choices(feature: str, option: str):
    """Spec 2.5: the key is the value that needs the service, so a typo would ask for nothing."""
    declared = _catalog()["features"][feature]["options"][option]
    services = declared.get("services", {})

    assert set(services) <= set(declared["choices"])
    assert services == EXTRA_SERVICES[(feature, option)]
    assert declared["default"] not in services


OPTION_SOURCES = {
    ("cache", "backend"): ("src/infrastructure/cache/initialize.py", "CacheBackend"),
    ("taskiq", "broker"): ("src/infrastructure/taskiq/settings.py", "TaskiqBrokerType"),
}
"""Where each option's choices are acted on, and the enum whose members name them."""


@pytest.mark.parametrize(("feature", "option"), sorted(OPTION_SOURCES))
def test_every_option_offers_the_values_its_feature_acts_on(feature: str, option: str):
    """`CacheBackend` also names an in-memory backend that nothing starts, so it isn't offered."""
    module, enum = OPTION_SOURCES[(feature, option)]
    acted_on = re.findall(rf"{enum}\.([A-Z_]+)\.value", (REPO_ROOT / "backend" / module).read_text())

    assert sorted(set(acted_on)) == sorted(
        choice.upper() for choice in _catalog()["features"][feature]["options"][option]["choices"]
    )


@pytest.mark.parametrize(("feature", "option"), sorted(OPTION_SOURCES))
def test_every_option_defaults_to_what_the_project_already_ships(feature: str, option: str):
    """The question `fastro new` asks pre-picks the value a clone of this repo runs with."""
    declared = _catalog()["features"][feature]["options"][option]
    example = (REPO_ROOT / "backend" / ".env.example").read_text()

    for variable in declared["env"]:
        assert f"\n{variable}={declared['default']}\n" in example


@pytest.mark.parametrize(("feature", "option"), sorted(OPTION_SOURCES))
def test_every_option_marks_the_line_it_rewrites(feature: str, option: str):
    """Spec 6.1: the marker sits on its own line directly above the VAR line it speaks for."""
    declared = _catalog()["features"][feature]["options"][option]
    lines = (REPO_ROOT / "backend" / ".env.example").read_text().splitlines()

    for variable in declared["env"]:
        marked = [index for index, line in enumerate(lines) if line == f"# @fastro option={feature}.{option}"]
        assert len(marked) == 1
        assert lines[marked[0] + 1].startswith(f"{variable}=")


SLOT_KINDS = {"tuple", "list", "class", "value", "reexport", "raw", "data"}
"""Spec 2.6. A kind the engine doesn't know would be a slot nothing renders."""


def _written_by_build(manifest: Any) -> list[str]:
    """The files `build` writes, read out of its source rather than listed again here."""
    source = inspect.getsource(manifest.build)

    return re.findall(r'\(project / "([^"]+)"\)\.write_text', source)


def _entries() -> list[dict[str, Any]]:
    return list(_catalog()["wiring"])


def _committed(path: str) -> str:
    return (REPO_ROOT / path).read_text()


def _annotated(source: str, name: str) -> str | None:
    """How the committed file spells this name's annotation."""
    for node in ast.parse(source).body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == name:
            return ast.unparse(node.annotation)

    return None


def test_the_wiring_entries_are_the_files_the_drill_writes():
    """One entry per generated file, both ways. The entries' order carries nothing, so it is free."""
    written = _written_by_build(_drill())

    assert sorted(entry["path"] for entry in _entries()) == sorted(written)
    assert len(written) == 12


@pytest.mark.parametrize("path", [entry["path"] for entry in _entries()])
def test_every_wiring_file_is_under_the_python_root_and_is_a_file(path: str):
    """Spec 2.6: a generated Python file lives under `python_root`, and names one file."""
    blueprint = _catalog()["blueprint"]

    assert path.startswith(blueprint["python_root"] + "/")
    assert not path.endswith("/")
    assert (REPO_ROOT / path).is_file()


@pytest.mark.parametrize(
    ("path", "name"),
    [(entry["path"], slot["name"]) for entry in _entries() for slot in entry["slots"] if "annotation" in slot],
)
def test_every_annotated_slot_is_annotated_the_way_the_file_annotates_it(path: str, name: str):
    """`NAME: ANNOTATION` is what mypy and an IDE read, so the catalog has to spell it the same."""
    slot = next(slot for slot in next(e for e in _entries() if e["path"] == path)["slots"] if slot.get("name") == name)

    assert _annotated(_committed(path), name) == slot["annotation"]


@pytest.mark.parametrize(
    ("path", "name"),
    [(entry["path"], slot["name"]) for entry in _entries() for slot in entry["slots"] if "name" in slot],
)
def test_every_slot_fills_a_name_the_file_defines(path: str, name: str):
    assert _defined(_committed(path), name) is not None or name in {alias for _, _, alias in _bindings(_committed(path))}


def test_every_declared_point_is_filled_by_exactly_one_slot():
    """One direction: a point no slot collects is a point whose contributions reach nothing."""
    filled = [slot["point"] for entry in _entries() for slot in entry["slots"] if "point" in slot]

    assert sorted(filled) == sorted(_catalog()["points"])


def test_every_slot_collects_a_point_the_catalog_declares():
    """The other direction: a slot naming an undeclared point would collect nothing for ever."""
    declared = set(_catalog()["points"])

    for entry in _entries():
        for slot in entry["slots"]:
            if slot["kind"] == "raw":
                assert "point" not in slot and "name" not in slot
                continue

            assert slot["point"] in declared, slot


@pytest.mark.parametrize(
    ("path", "kind"),
    [(entry["path"], slot["kind"]) for entry in _entries() for slot in entry["slots"]],
)
def test_every_slot_is_a_kind_the_spec_has(path: str, kind: str):
    assert kind in SLOT_KINDS


def test_every_point_a_project_fills_once_is_rendered_as_one_value():
    """Spec 2.6: `value`, `class` and `reexport` render one, and each needs its fallback."""
    cardinality = {name: point["cardinality"] for name, point in _catalog()["points"].items()}

    for entry in _entries():
        for slot in entry["slots"]:
            if slot["kind"] in {"value", "reexport"}:
                assert cardinality[slot["point"]] == "one", slot
                assert "fallback" in slot, slot
            if slot["kind"] in {"tuple", "list"}:
                assert cardinality[slot["point"]] == "many", slot


def test_the_file_a_feature_brings_with_it_is_generated_only_for_that_feature():
    """FR003: without admin the file is absent from the project, not emptied."""
    admin = next(entry for entry in _entries() if entry["path"].endswith("wiring/admin.py"))
    build = inspect.getsource(_drill().build)

    assert admin["if"] == "admin"
    assert 'if "admin" in chosen:' in build
    assert [entry.get("if") for entry in _entries()].count(None) == 11


def test_the_statement_a_raw_slot_carries_is_in_the_file():
    """`settings = Settings()` is what the rest of the project imports, and no point fills it."""
    raw = [slot for entry in _entries() for slot in entry["slots"] if slot["kind"] == "raw"]
    committed = _committed("backend/src/wiring/settings.py")

    assert [slot["code"] for slot in raw] == ["settings = Settings()"]
    assert "settings = Settings()" in committed


def _declared_bindings(catalog: dict[str, Any], entry: dict[str, Any], chosen: set[str]) -> set[tuple[str, str, str]]:
    """Every name the catalog says this file binds: its own imports, and what reaches its slots."""
    bindings: set[tuple[str, str, str]] = set()
    for line in entry.get("imports", ()):
        module, _, names = line.removeprefix("from ").partition(" import ")
        bindings.update((module, name, name) for name in names.split(", "))

    for slot in entry["slots"]:
        if slot["kind"] == "raw":
            continue

        contributed = _contributed(catalog, slot["point"], chosen)
        if contributed and not slot.get("literal"):
            bindings.update(_binding(contribution["ref"]) for contribution in contributed if "ref" in contribution)
            for line in slot.get("item_imports", ()):
                module, _, names = line.removeprefix("from ").partition(" import ")
                bindings.update((module, name, name) for name in names.split(", "))

        if not contributed:
            for line in slot.get("fallback_imports", ()):
                module, _, names = line.removeprefix("from ").partition(" import ")
                bindings.update((module, name, name) for name in names.split(", "))
            if ":" in slot.get("fallback", ""):
                bindings.add(_binding(slot["fallback"]))

        bindings.update(_binding(ref) for ref in slot.get("append", ()))

    return bindings


@pytest.mark.parametrize("path", [entry["path"] for entry in _entries()])
def test_the_catalog_accounts_for_every_name_the_file_imports(path: str):
    """An import the entry forgets is a NameError in a project nobody has built yet.

    The committed files carry every feature, so with everything selected the names the
    catalog brings and the names the file binds are the same set, both ways.
    """
    catalog = _catalog()
    entry = next(entry for entry in _entries() if entry["path"] == path)

    assert _declared_bindings(catalog, entry, set(catalog["features"])) == _bindings(_committed(path))


def _refs_of(slot: dict[str, Any]) -> list[str]:
    """The refs a slot names itself: its fallback, and the bases it always appends."""
    refs = list(slot.get("append", ()))
    if ":" in slot.get("fallback", ""):
        refs.append(slot["fallback"])

    return refs


def test_every_ref_a_slot_names_itself_exists():
    """A fallback is what a project without the feature gets, so it has to be importable there."""
    named = [(entry["path"], ref) for entry in _entries() for slot in entry["slots"] for ref in _refs_of(slot)]

    assert sorted(ref for _, ref in named) == [
        "pydantic:BaseModel",
        "src.infrastructure.config.base:CoreSettings",
        "src.infrastructure.uncached:cached",
    ]

    for path, ref in named:
        module, attribute, _ = _ref(ref)
        if module.startswith("src."):
            assert _defines(module, attribute), (path, ref)
        else:
            assert hasattr(importlib.import_module(module), attribute), (path, ref)


def test_every_import_a_fallback_needs_names_something_that_exists():
    """Spec 2.6: these lines are emitted only when the fallback is used, so nothing else checks them."""
    lines = [
        (entry["path"], line) for entry in _entries() for slot in entry["slots"] for line in slot.get("fallback_imports", ())
    ]

    assert len(lines) == 2

    for path, line in lines:
        module, _, name = line.removeprefix("from ").partition(" import ")
        assert path.startswith("backend/src/wiring/"), path
        assert _defines("src." + module.lstrip("."), name), line


def test_the_header_every_generated_file_carries_is_fastros_own():
    """Spec 2.12, verbatim: a project's wiring says what wrote it and how to change it."""
    assert _catalog()["wiring_defaults"]["header"] == (
        "Generated by fastro from blueprint.toml and fastro.toml. Don't edit: change\n"
        "fastro.toml (or [app] in it, for your own code) and run `fastro sync`."
    )


def test_the_header_fits_the_line_length_of_the_files_it_goes_into():
    """Spec 2.8: each line is at most 100 characters, so a docstring passes E501 at 128."""
    for line in _catalog()["wiring_defaults"]["header"].splitlines():
        assert len(line) <= 100, line


HAND_WRITTEN = "backend/src/wiring/__init__.py"
"""The one module beside the generated ones that a person writes, and fastro never rewrites."""


def _docstring(source: str) -> str | None:
    """The module docstring as it is written, rather than as ``ast`` tidies it up."""
    body = ast.parse(source).body
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
        return str(body[0].value.value)

    return None


@pytest.mark.parametrize("path", [entry["path"] for entry in _entries()])
def test_every_generated_file_carries_its_doc_and_then_the_header(path: str):
    """Spec 2.8: the entry's `doc`, a blank line, then the header, each stripped before rendering.

    This is the whole docstring, so a paragraph the file carries and the catalog doesn't is one
    `fastro sync` would delete from a project without being asked.
    """
    entry = next(declared for declared in _entries() if declared["path"] == path)
    header = _catalog()["wiring_defaults"]["header"]

    assert _docstring(_committed(path)) == f"{entry['doc'].strip()}\n\n{header.strip()}\n"


@pytest.mark.parametrize("path", [entry["path"] for entry in _entries()])
def test_no_generated_file_names_the_drill(path: str):
    """The header names fastro as the author, and the drill goes in B3: two authors is one too many."""
    assert "removal_drill" not in _committed(path), path


def test_the_hand_written_module_says_who_writes_the_ones_beside_it():
    """It is not generated, so it is where the reason lives: once, in the file a person edits."""
    docstring = _docstring(_committed(HAND_WRITTEN))

    assert HAND_WRITTEN not in [entry["path"] for entry in _entries()]
    assert docstring is not None
    assert "fastro" in docstring
    assert "blueprint.toml" in docstring
    assert "imports and literals" in docstring
    assert "removal_drill" not in docstring


@pytest.mark.parametrize("path", [entry["path"] for entry in _entries()])
def test_the_catalog_accounts_for_what_the_file_imports_for_every_selection(path: str):
    """The fallbacks, where the committed files cannot reach: nothing falls back with all nine.

    `fallback_imports`, the pydantic base and the uncached decorator are only written into a
    project that left the feature out, so only a smaller selection compares them.
    """
    catalog = _catalog()
    manifest = _drill()
    entry = next(entry for entry in _entries() if entry["path"] == path)
    generator = next(
        drill_generator
        for point, (drill_generator, _) in POINTS.items()
        if any(slot.get("point") == point for slot in entry["slots"])
    )

    for chosen in _selections(manifest):
        if generator == "_wiring_admin" and "admin" not in chosen:
            continue

        written = _bindings(_written_for(manifest, generator, chosen))
        assert _declared_bindings(catalog, entry, chosen) == written, sorted(chosen)


LINE_LENGTH = 128
"""The project's ruff line length, which spec 2.8 wraps a generated import at."""


@pytest.mark.parametrize("path", [entry["path"] for entry in _entries()])
def test_no_import_in_a_generated_file_is_wrapped_before_it_has_to_be(path: str):
    """Spec 2.8: a statement is wrapped only when one line of it would be too long."""
    source = _committed(path)
    for node in ast.parse(source).body:
        if not isinstance(node, ast.Import | ast.ImportFrom):
            continue

        one_line = ast.unparse(node)
        wrapped = (node.end_lineno or node.lineno) > node.lineno
        assert wrapped == (len(one_line) > LINE_LENGTH), one_line


@pytest.mark.parametrize(
    ("path", "name"),
    [(entry["path"], slot["name"]) for entry in _entries() for slot in entry["slots"] if slot["kind"] in {"tuple", "list"}],
)
def test_a_collection_of_more_than_one_is_written_one_entry_to_a_line(path: str, name: str):
    """Spec 2.6: a tuple of two or more is always exploded, and a list always is."""
    slot = next(slot for slot in next(e for e in _entries() if e["path"] == path)["slots"] if slot.get("name") == name)
    defined = _defined(_committed(path), name)

    assert isinstance(defined, ast.Tuple | ast.List)
    exploded = (defined.end_lineno or defined.lineno) > defined.lineno

    assert exploded == (len(defined.elts) >= (1 if slot["kind"] == "list" else 2))


PROJECT_FILE = REPO_ROOT / "fastro.toml"

GENERATOR_NAME = re.compile(r"^[a-z][a-z0-9-]*$")
"""Spec 2.9. It becomes the word after `fastro make`, and `fastro make` takes no underscore."""

COMMAND_WORD = re.compile(r"^[a-z][a-z0-9-]*$")

PARAM_TYPES = {"int", "str", "bool", "cidr", "choice"}

PYTHON_TYPES: dict[str, type] = {"int": int, "str": str, "bool": bool, "cidr": str, "choice": str}


@functools.cache
def _project() -> dict[str, Any]:
    with PROJECT_FILE.open("rb") as handle:
        return tomllib.load(handle)


def _owned_paths() -> set[str]:
    return {path for feature in _catalog()["features"].values() for path, _ in _declared(feature)}


@pytest.mark.parametrize("name", sorted(_catalog()["generators"]))
def test_every_generator_is_named_the_way_fastro_make_reads_it(name: str):
    assert GENERATOR_NAME.match(name)
    assert "register" not in _catalog()["generators"][name] or name == "module"
    assert "types" not in _catalog()["generators"][name] or name == "module"


@pytest.mark.parametrize("name", sorted(_catalog()["generators"]))
def test_every_generators_templates_are_a_directory_this_repo_has(name: str):
    """Spec 2.9: subdirectories when the generator has modes, which is one tree per mode."""
    generator = _catalog()["generators"][name]
    templates = REPO_ROOT / generator["templates"]

    assert templates.is_dir()
    assert any(child.is_dir() for child in templates.iterdir())


def test_the_deploy_modes_are_the_ones_this_repo_can_generate():
    """A mode with no template tree would be offered and then fail; a tree with no mode is dead."""
    templates = REPO_ROOT / _catalog()["generators"]["deploy"]["templates"]
    offered = re.findall(r"^    (\w+) = \"\w+\"$", (REPO_ROOT / "cli/src/cli/commands/deploy.py").read_text(), re.M)

    assert sorted(child.name for child in templates.iterdir() if child.is_dir()) == sorted(offered)


@pytest.mark.parametrize(
    ("generator", "param"),
    sorted((name, param) for name, declared in _catalog()["generators"].items() for param in declared["params"]),
)
def test_every_param_is_declared_the_way_the_spec_asks(generator: str, param: str):
    """Spec 2.9: a type and a default of that type, and the keys each type allows."""
    declared = _catalog()["generators"][generator]["params"][param]

    assert FEATURE_NAME.match(param)
    assert declared["type"] in PARAM_TYPES
    assert isinstance(declared["default"], PYTHON_TYPES[declared["type"]])
    assert declared["type"] == "bool" or not isinstance(declared["default"], bool), "a bool is an int to isinstance"
    assert declared["help"].strip() == declared["help"]
    assert ("choices" in declared) == (declared["type"] == "choice")
    for key in ("private_only", "max_prefix"):
        assert key not in declared or declared["type"] == "cidr"


def test_the_subnet_default_is_a_network_with_no_host_bits_set():
    """Spec 2.9: `10.0.0.1/24` is not a network, and the tool would refuse the catalog for it."""
    declared = _catalog()["generators"]["deploy"]["params"]["internal_subnet"]

    assert str(ipaddress.ip_network(declared["default"], strict=True)) == declared["default"]
    assert 0 <= declared["max_prefix"] <= 128


def test_every_param_the_templates_read_is_a_param_the_catalog_declares():
    """Both ways: an undeclared param is a StrictUndefined crash, a declared one nothing reads is dead."""
    generator = _catalog()["generators"]["deploy"]
    templates = REPO_ROOT / generator["templates"]
    read = {name for template in templates.rglob("*.j2") for name in re.findall(r"params\.([a-z_]+)", template.read_text())}

    assert read == set(generator["params"])


def test_the_defaults_are_what_this_repos_own_generator_already_uses():
    """`fastro make deploy` has to write what `bp deploy generate` writes, or the first run changes."""
    params = _catalog()["generators"]["deploy"]["params"]
    source = (REPO_ROOT / "cli/src/cli/commands/deploy.py").read_text()
    subnet = (REPO_ROOT / "cli/src/cli/features/_builtins/deploy/feature.py").read_text()

    assert f'typer.Option({params["api_port"]["default"]}, "--api-port"' in source
    assert f'typer.Option({params["workers"]["default"]}, "--workers"' in source
    assert f'DEFAULT_INTERNAL_SUBNET = "{params["internal_subnet"]["default"]}"' in subnet


def _declared_commands() -> list[tuple[str | None, str, dict[str, Any]]]:
    """Every declared command: the feature that owns it, or none, with its words and its table.

    A list rather than a table keyed by the words, because two declarations of one command are
    what spec 2.9 refuses, and a table would quietly keep the second.
    """
    declared: list[tuple[str | None, str, dict[str, Any]]] = [
        (None, words, command) for words, command in _catalog()["commands"].items()
    ]
    for name, feature in _catalog()["features"].items():
        declared.extend((name, words, command) for words, command in feature.get("commands", {}).items())

    return declared


def _script_of(command: dict[str, Any]) -> str:
    return f"{_catalog()['blueprint']['python_root']}/{Path(*command['module'].split('.')).with_suffix('.py')}"


def _under(script: str, paths: Iterable[str]) -> bool:
    """Spec 1.1: a declaration names the file itself, or a subtree it sits in."""
    return any(script == path or script.startswith(f"{path}/") for path in paths)


def _sorted_commands() -> list[tuple[str | None, str, dict[str, Any]]]:
    return sorted(_declared_commands(), key=lambda entry: entry[1])


COMMANDS = [pytest.param(words, command, id=words) for _, words, command in _sorted_commands()]

TOP_LEVEL_COMMANDS = [pytest.param(words, command, id=words) for owner, words, command in _sorted_commands() if owner is None]

FEATURE_COMMANDS = [
    pytest.param(owner, words, command, id=words) for owner, words, command in _sorted_commands() if owner is not None
]


@pytest.mark.parametrize(("words", "command"), COMMANDS)
def test_every_command_is_spelled_the_way_the_spec_reads_it(words: str, command: dict[str, Any]):
    """Spec 2.9: the words become the command path, one space apart."""
    assert all(COMMAND_WORD.match(word) for word in words.split(" "))
    assert "  " not in words
    assert all(part.isidentifier() and not keyword.iskeyword(part) for part in command["module"].split("."))
    assert command["help"].strip() == command["help"]
    assert "\n" not in command["help"]
    assert command.get("outside_project", "error") in {"error", "token_hex"}


@pytest.mark.parametrize(("words", "command"), COMMANDS)
def test_every_command_runs_a_module_this_repo_can_run(words: str, command: dict[str, Any]):
    """It is run as `python -m <module>`, which needs the entry point that makes that work."""
    path = REPO_ROOT / _catalog()["blueprint"]["python_root"] / Path(*command["module"].split(".")).with_suffix(".py")

    assert path.is_file(), words
    assert '__name__ == "__main__"' in path.read_text()


def test_no_two_commands_claim_the_same_words():
    """Spec 2.9: the words are unique across `[commands]` and every feature's.

    fastro refuses the catalog at the second declaration, so a repeat is a catalog no project
    can be generated from at all.
    """
    claimed = [words for _, words, _ in _declared_commands()]

    assert sorted(claimed) == sorted(set(claimed))


@pytest.mark.parametrize(("words", "command"), TOP_LEVEL_COMMANDS)
def test_every_command_runs_a_script_no_feature_takes_away(words: str, command: dict[str, Any]):
    """`[commands]` are always present (spec 2.9), so one naming a feature's script would break.

    `scripts/unlock_account.py` goes with accounts, so it is accounts that declares
    `fastro users unlock`: top-level, the command would be there in a project without the
    module it runs.
    """
    assert not _under(_script_of(command), _owned_paths()), words


@pytest.mark.parametrize(("owner", "words", "command"), FEATURE_COMMANDS)
def test_every_feature_command_sits_under_its_features_own_paths(owner: str, words: str, command: dict[str, Any]):
    """Spec 2.9: under the feature's own `paths`, not a `when`'s, which a selection still drops."""
    declared = _declared(_catalog()["features"][owner])
    script = _script_of(command)

    assert _under(script, [path for path, condition in declared if condition is None]), words
    assert not _under(script, [path for path, condition in declared if condition is not None]), words


def test_the_feature_commands_are_every_feature_owned_script_a_project_could_run():
    """Both ways, and against the repository rather than against the catalog's own account.

    A runnable script of a feature's own that nothing declares is a command no project is
    offered, and a command for a module its feature doesn't own is one some project is left
    without.
    """
    python_root = _catalog()["blueprint"]["python_root"]
    directory = REPO_ROOT / python_root / "scripts"
    runnable = {
        f"{python_root}/scripts/{script.name}"
        for script in sorted(directory.glob("*.py"))
        if _under(f"{python_root}/scripts/{script.name}", _owned_paths()) and '__name__ == "__main__"' in script.read_text()
    }

    assert runnable, directory
    assert {_script_of(command) for owner, _, command in _declared_commands() if owner is not None} == runnable


def test_every_selection_carries_the_commands_whose_module_it_keeps():
    """A feature's command is there only where the feature is (spec 2.4).

    That has to be exactly where the module it runs is still on disk: a command offered by a
    project that cannot run it is worse than no command, and one a project could run but is
    never offered is work thrown away.
    """
    manifest = _drill()
    owned = _owned_paths()

    for chosen in _selections(manifest):
        kept = _kept_by_the_drill(manifest, chosen)
        offered = {words for owner, words, _ in _declared_commands() if owner is None or owner in chosen}
        runnable = {
            words
            for _, words, command in _declared_commands()
            if not _under(_script_of(command), owned) or _under(_script_of(command), kept)
        }

        assert offered == runnable, sorted(chosen)


def test_the_blueprint_repo_says_it_is_the_blueprint():
    """Spec 3: `source = true` only in a blueprint repo, where generated files are committed."""
    assert _project()["source"] is True
    assert _project()["blueprint"] == {"name": _catalog()["blueprint"]["name"], "version": _catalog()["blueprint"]["version"]}


def test_the_blueprint_repo_carries_every_feature():
    """It has to: the committed wiring is the `everything` selection, and the tests cover all nine."""
    assert _project()["features"] == list(_catalog()["features"])


def test_the_blueprint_repo_runs_every_option_at_its_default():
    """Spec 6.1: the `.env.example` lines the options rewrite are the ones this repo ships."""
    declared = {
        f"{name}.{option}": option_table["default"]
        for name, feature in _catalog()["features"].items()
        for option, option_table in feature.get("options", {}).items()
    }

    assert _project()["options"] == declared


def test_the_project_is_named_the_way_its_python_package_is():
    """`project.name` is what the deploy templates name the compose project after (spec 6.2)."""
    with BACKEND_PYPROJECT.open("rb") as handle:
        backend = tomllib.load(handle)

    assert _project()["project"]["name"] == backend["project"]["name"]
