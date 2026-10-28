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
import itertools
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

SET_NAME = re.compile(r"^[a-z][a-z0-9_-]*$")
"""Spec 1.2. A preset or a verify set may carry a hyphen, which a feature name may not."""

NOT_YET_WRITTEN = {"fastro.toml"}
"""`fastro.toml` is declared in the catalog before it exists."""


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


@pytest.mark.parametrize("path", [entry["path"] for entry in _entries()])
def test_every_wiring_file_says_what_it_is_for(path: str):
    """The entry's `doc` is the file's own docstring, minus the line naming what generated it."""
    entry = next(entry for entry in _entries() if entry["path"] == path)
    docstring = ast.get_docstring(ast.parse(_committed(path)))

    assert docstring is not None
    declared = entry["doc"].splitlines()
    assert declared[0] == docstring.splitlines()[0]
    assert " ".join(" ".join(declared[1:]).split()) in " ".join(docstring.split())


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
