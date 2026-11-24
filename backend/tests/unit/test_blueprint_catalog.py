"""The catalog describes this repository.

`blueprint.toml` is read by fastro, which the repository root installs and the backend doesn't,
so nothing in this file imports it: the rules it checks are transcribed from the catalog spec,
and the facts it checks against are the repository's own files.
"""

import ast
import fnmatch
import functools
import importlib
import ipaddress
import itertools
import keyword
import re
import subprocess
import sys
import time
import tomllib
from collections.abc import Iterable
from importlib.metadata import packages_distributions, requires
from pathlib import Path
from typing import Any

import pytest
import yaml
from packaging.requirements import Requirement

from tests.conftest import is_docker_running

REPO_ROOT = Path(__file__).resolve().parents[3]


def _git_listing(*arguments: str) -> set[str]:
    listed = subprocess.run(["git", "ls-files", "-z", *arguments], cwd=REPO_ROOT, capture_output=True, text=True, check=True)

    return set(filter(None, listed.stdout.split("\0")))


@functools.cache
def _tracked_files() -> tuple[Path, ...]:
    """Every file git tracks and still has, which is what fastro reads the blueprint from.

    The scans here read these and nothing else, so no untracked folder, a virtualenv, a build
    or a cache, can change what they find."""
    return tuple(REPO_ROOT / name for name in sorted(_git_listing() - _git_listing("--deleted")))


def _tracked(directory: Path, pattern: str = "*.py", *, recursive: bool = True) -> list[Path]:
    """The tracked files under ``directory`` whose name matches ``pattern``, in order."""
    return [
        path
        for path in _tracked_files()
        if (path.is_relative_to(directory) if recursive else path.parent == directory) and fnmatch.fnmatch(path.name, pattern)
    ]


def _is_tracked_file(path: Path) -> bool:
    return path in _tracked_files()


def _is_tracked_dir(path: Path) -> bool:
    """Whether ``path`` holds a tracked file, which is what git, and fastro, call a directory."""
    return any(file != path and file.is_relative_to(path) for file in _tracked_files())


def _is_tracked(path: Path) -> bool:
    return _is_tracked_file(path) or _is_tracked_dir(path)


CATALOG = REPO_ROOT / "blueprint.toml"
BACKEND_PYPROJECT = REPO_ROOT / "backend" / "pyproject.toml"

FEATURE_NAME = re.compile(r"^[a-z][a-z0-9_]*$")
"""Spec 1.2. Written out rather than imported, because the backend's tests don't import fastro."""

BLUEPRINT_NAME = re.compile(r"^[a-z][a-z0-9-]*$")

SET_NAME = re.compile(r"^[a-z][a-z0-9_-]*$")
"""Spec 1.2. A preset or a verify set may carry a hyphen, which a feature name may not."""


@functools.cache
def _catalog() -> dict[str, Any]:
    with CATALOG.open("rb") as handle:
        return tomllib.load(handle)


def test_the_catalog_parses():
    assert _catalog()["blueprint"]["name"] == "fastapi-boilerplate"


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


def _declared_specifiers(listing: str = "runtime") -> set[str]:
    """Every specifier a project could install from this listing: the core's, each feature's, each
    `when` block's, and, for the runtime one, each option's."""
    key = "dependencies" if listing == "runtime" else "dev_dependencies"
    specifiers = set(_catalog()["blueprint"]["dependencies"][listing])
    for feature in _catalog()["features"].values():
        specifiers.update(feature.get(key, ()))
        for block in feature.get("when", ()):
            specifiers.update(block.get(key, ()))
        for option in feature.get("options", {}).values() if listing == "runtime" else ():
            for chosen in option.get("dependencies", {}).values():
                specifiers.update(chosen)

    return specifiers


def test_the_dependencies_a_project_could_install_are_the_ones_the_backend_declares():
    """This repo selects every feature, so the union of the declarations is the backend's own list.

    The specifiers are compared, not the distribution names, so a floor that moves in one file
    and not the other is caught rather than averaged away.
    """
    with BACKEND_PYPROJECT.open("rb") as handle:
        backend = tomllib.load(handle)

    assert _declared_specifiers() == set(backend["project"]["dependencies"])
    assert _declared_specifiers("dev") == set(backend["project"]["optional-dependencies"]["dev"])


FASTAPI_THE_APP_NEEDS = {
    "get_flat_dependant": ("src/infrastructure/cache/utils.py", "0.140.7"),
    "openapi_prefix": ("src/infrastructure/app_factory.py", "0.145.0"),
}
"""Each FastAPI name the app relies on, the file that uses it, and the first release without it."""


def test_every_fastapi_a_project_could_install_is_one_the_app_can_import():
    """A project resolves its dependencies fresh, so the declared range, not the lock, decides which FastAPI it gets."""
    with (REPO_ROOT / "uv.lock").open("rb") as handle:
        locked = next(package["version"] for package in tomllib.load(handle)["package"] if package["name"] == "fastapi")
    ranges = [Requirement(specifier).specifier for specifier in _declared_specifiers() if _distribution(specifier) == "fastapi"]

    assert ranges
    for name, (path, first_without) in FASTAPI_THE_APP_NEEDS.items():
        assert name in (REPO_ROOT / "backend" / path).read_text(), (name, path)
        for allowed in ranges:
            assert first_without not in allowed, (allowed, name)
    for allowed in ranges:
        assert "999.0" not in allowed, allowed
        assert locked in allowed, (allowed, locked)


def _distribution(specifier: str) -> str:
    """The distribution a PEP 508 specifier names, without its extras or its version."""
    return re.split(r"[\[<>=!~;]", specifier)[0].strip().lower().replace("_", "-")


@functools.cache
def _provided() -> dict[str, frozenset[str]]:
    """The modules each installed distribution provides, which is what an import names: `faker`
    is imported as `faker`, and `user-agents` as `user_agents`."""
    provided: dict[str, set[str]] = {}
    for module, distributions in packages_distributions().items():
        for distribution in distributions:
            provided.setdefault(_distribution(distribution), set()).add(module)

    return {name: frozenset(modules) for name, modules in provided.items()}


@functools.cache
def _module_imports(path: Path) -> frozenset[str]:
    """Every module an absolute import in this file names, dotted as it is written."""
    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            found.add(node.module)

    return frozenset(found)


@functools.cache
def _imported(*directories: str, skipping: tuple[str, ...] = ()) -> frozenset[str]:
    """Every top-level module imported under these directories of the python root, less the files
    named in `skipping`, which are given relative to that root."""
    root = REPO_ROOT / _catalog()["blueprint"]["python_root"]
    skipped = {root / name for name in skipping}

    return frozenset(
        module.split(".")[0]
        for directory in directories
        for path in _tracked(root / directory)
        if path not in skipped
        for module in _module_imports(path)
    )


@functools.cache
def _imports_outright(path: Path) -> frozenset[str]:
    """The top-level modules this file imports with no guard, counted statement by statement.

    One import of a module inside a `try` doesn't excuse another outside it: the unguarded one is
    what runs first and what fails, so a module imported both ways is imported outright.
    """
    tree = ast.parse(path.read_text())
    guarded = {
        id(inner)
        for node in ast.walk(tree)
        if isinstance(node, ast.Try)
        for inner in ast.walk(node)
        if isinstance(inner, ast.Import | ast.ImportFrom)
    }

    found: set[str] = set()
    for node in ast.walk(tree):
        if id(node) in guarded:
            continue

        if isinstance(node, ast.Import):
            found.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            found.add(node.module.split(".")[0])

    return frozenset(found)


@functools.cache
def _importers() -> dict[str, frozenset[str]]:
    """Which files under the python root import each top-level module, as repo-relative paths."""
    root = REPO_ROOT / _catalog()["blueprint"]["python_root"]
    found: dict[str, set[str]] = {}
    for path in _tracked(root):
        for module in _module_imports(path):
            found.setdefault(module.split(".")[0], set()).add(path.relative_to(REPO_ROOT).as_posix())

    return {module: frozenset(files) for module, files in found.items()}


def _declared_distributions(listing: str) -> set[str]:
    """The distributions a listing names, the core's and every feature's together."""
    return {_distribution(specifier) for specifier in _declared_specifiers(listing)}


INDIRECT_NEEDS = {
    "itsdangerous": ("starlette.middleware.sessions", "backend/src/interfaces/admin/auth.py"),
    "user-agents": ("crudauth.transports.session.transport", "backend/src/infrastructure/auth/evictions.py"),
}
"""Distributions nothing imports by name, each with the import that needs it and the file that
makes that import. `starlette` doesn't declare `itsdangerous`, and importing
`crudauth.transports.session.transport` runs that package's `__init__`, which imports its
`manager`, which imports `user_agents` inside a `try`. A project without either would refuse
to start the admin panel, or record every session's device as unknown, with nothing naming
what is missing."""


NEEDED_WITHOUT_AN_IMPORT = {
    "asyncpg": "the driver `POSTGRES_ASYNC_PREFIX` names, which sqlalchemy loads from the URL",
    "greenlet": "what sqlalchemy runs a DBAPI call in, for its asyncio support",
}
"""Core distributions no file imports and no import pulls in: another distribution asks for them,
or a setting names them as a driver. Written down so a project's image carries nothing nobody can
account for."""


def test_every_runtime_dependency_nothing_imports_is_accounted_for():
    """Both ways: a distribution installed and never imported is either needed through something
    else, which is worth writing down, or weight in every project's image for no reason."""
    runtime = _declared_distributions("runtime")
    imported = {name for name in runtime if _provided().get(name, frozenset()) & set(_importers())}

    assert runtime - imported == set(INDIRECT_NEEDS) | set(NEEDED_WITHOUT_AN_IMPORT)


def test_the_two_the_database_needs_are_the_blueprint_s_to_declare():
    """Why neither can be left to sqlalchemy, read from the installed metadata and the settings.

    `asyncpg` is the driver the URL names and sqlalchemy loads; `greenlet` is what sqlalchemy's
    asyncio support runs a driver's calls in. Sqlalchemy asks for them only through extras the
    backend doesn't declare, and the greenlet one outright on some platforms only, so a project
    that installed plain `sqlalchemy` would have neither.
    """
    asked = requires("sqlalchemy") or ()
    base = (REPO_ROOT / "backend/src/infrastructure/config/base.py").read_text()

    assert 'POSTGRES_ASYNC_PREFIX: str = "postgresql+asyncpg://"' in base
    assert any(entry.startswith("asyncpg") and entry.endswith('extra == "postgresql-asyncpg"') for entry in asked)
    assert any(entry.startswith("greenlet") and entry.endswith('extra == "asyncio"') for entry in asked)
    assert "sqlalchemy>=2.0.37" in _catalog()["blueprint"]["dependencies"]["runtime"], "plain, with no extras"


@pytest.mark.parametrize(
    ("feature", "specifier"),
    sorted(
        (name, specifier) for name, feature in _catalog()["features"].items() for specifier in feature.get("dependencies", ())
    ),
)
def test_every_feature_dependency_is_one_that_feature_needs(feature: str, specifier: str):
    """A dependency parked on the wrong feature is a project that installs it and never uses it,
    or selects the feature and finds it missing."""
    name = _distribution(specifier)
    owned = [path for path, _ in _declared(_catalog()["features"][feature])]

    if name in INDIRECT_NEEDS:
        module, importer = INDIRECT_NEEDS[name]

        assert _under(importer, owned), importer
        assert module in _module_imports(REPO_ROOT / importer), module
        assert not _provided()[name] & set(_importers()), f"{name} is imported by name now"

        return

    importers = {file for module in _provided()[name] for file in _importers().get(module, ())}
    outright = {file for file in importers if _provided()[name] & _imports_outright(REPO_ROOT / file)}

    assert importers, name
    assert any(_under(file, owned) for file in outright), sorted(importers)


def _needed_by(features: dict[str, Any]) -> dict[str, set[str]]:
    """Each declared distribution, with the features that bring it. An option's brings an empty
    set: a project selects the feature and still chooses another value, so nothing guarantees it."""
    needed: dict[str, set[str]] = {}
    for name, feature in features.items():
        for specifier in feature.get("dependencies", ()):
            needed.setdefault(_distribution(specifier), set()).add(name)
        for option in feature.get("options", {}).values():
            for specifiers in option.get("dependencies", {}).values():
                for specifier in specifiers:
                    needed.setdefault(_distribution(specifier), set())

    return needed


def _removed_for(features: dict[str, Any], chosen: set[str]) -> list[str]:
    """The owned paths this selection doesn't keep, which is what `_kept_by_the_catalog` leaves out."""
    return [
        path
        for name, feature in features.items()
        for path, condition in _declared(feature)
        if name not in chosen or (condition is not None and not _true(condition, chosen))
    ]


def test_no_file_a_project_keeps_imports_a_dependency_it_did_not_select():
    """The other half of moving a dependency off the core, over all 164 selections.

    `fastro new` writes a project's `pyproject.toml` from the declarations (spec 6.3), so a file
    kept without the feature that brings a distribution, importing it outright, is a project that
    fails at import. Only the files that go with the feature may need it.
    """
    features = _catalog()["features"]
    needed = _needed_by(features)

    assert needed["sqladmin"] == {"admin"}
    assert needed["aiomcache"] == set(), "an option's dependency is never guaranteed"

    for chosen in _selections():
        removed = _removed_for(features, chosen)
        for name, owners in needed.items():
            if owners & chosen:
                continue

            for module in _provided()[name]:
                for file in _importers().get(module, ()):
                    if not _provided()[name] & _imports_outright(REPO_ROOT / file):
                        continue

                    assert _under(file, removed) or _withheld(file), (sorted(chosen), name, file)


@functools.cache
def _project_modules_imported(file: str) -> frozenset[str]:
    """The project's own modules this file imports, as repo-relative paths with no suffix.

    A relative import is resolved against the file's package, and each name a `from` import takes
    counts as a submodule too, since it may be one.
    """
    root = _catalog()["blueprint"]["python_root"]
    tops = {
        path.relative_to(REPO_ROOT / root).parts[0]
        for path in _tracked(REPO_ROOT / root, "*")
        if len(path.relative_to(REPO_ROOT / root).parts) > 1
    }
    package = Path(file).relative_to(root).parts[:-1]
    found: set[tuple[str, ...]] = set()
    for node in ast.walk(ast.parse((REPO_ROOT / file).read_text())):
        if isinstance(node, ast.Import):
            found.update(tuple(alias.name.split(".")) for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            anchor = package[: len(package) - node.level + 1] if node.level else ()
            base = anchor + (tuple(node.module.split(".")) if node.module else ())
            found.add(base)
            found.update((*base, alias.name) for alias in node.names)

    return frozenset(f"{root}/{'/'.join(parts)}" for parts in found if parts and parts[0] in tops)


def test_no_file_a_project_keeps_imports_a_module_the_selection_removed():
    """Over all 164 selections, a kept file never imports the project's own code from a path a
    feature left out took with it: that project fails at import, or ships a test that can't.

    The generated wiring is left out here, since fastro writes it for each selection.
    """
    features = _catalog()["features"]
    generated = {entry["path"] for entry in _entries()}
    root = REPO_ROOT / _catalog()["blueprint"]["python_root"]
    files = [path.relative_to(REPO_ROOT).as_posix() for path in _tracked(root)]
    broken: dict[str, set[str]] = {}

    for chosen in _selections():
        removed = _removed_for(features, chosen)
        for file in files:
            if file in generated or _withheld(file) or _under(file, removed):
                continue
            for module in _project_modules_imported(file):
                if _under(module, removed) or _under(f"{module}.py", removed):
                    broken.setdefault(file, set()).add(",".join(sorted(chosen)))

    assert {file: len(selections) for file, selections in broken.items()} == {}


@pytest.mark.parametrize(
    ("feature", "specifier"),
    sorted(
        (name, specifier)
        for name, feature in _catalog()["features"].items()
        for specifier in feature.get("dev_dependencies", ())
    ),
)
def test_every_feature_development_dependency_belongs_to_that_feature(feature: str, specifier: str):
    """An extra is never imported by name, so what makes it the feature's is the distribution it
    extends: `taskiq[reload]` is the taskiq worker's own `--reload`, and a project with no worker
    has nothing to reload. A file of the feature's importing it counts too, for a test-only
    dependency that is imported.
    """
    name = _distribution(specifier)
    runtime = {_distribution(entry) for entry in _catalog()["features"][feature].get("dependencies", ())}
    owned = [path for path, _ in _declared(_catalog()["features"][feature])]
    importers = {file for module in _provided().get(name, ()) for file in _importers().get(module, ())}

    assert name in runtime or any(_under(file, owned) for file in importers), name


@pytest.mark.parametrize(
    ("feature", "option", "value", "specifier"),
    sorted(
        (name, option, value, specifier)
        for name, feature in _catalog()["features"].items()
        for option, declared in feature.get("options", {}).items()
        for value, specifiers in declared.get("dependencies", {}).items()
        for specifier in specifiers
    ),
)
def test_every_option_dependency_is_one_its_value_needs(feature: str, option: str, value: str, specifier: str):
    """Spec 2.5: the value has to be one of the option's choices, and the file that imports the
    distribution has to belong to the feature that offers it. A file that ships only with this
    value imports it plainly; any other has to guard the import, since a project that chose
    another value doesn't install it."""
    declared = _catalog()["features"][feature]["options"][option]
    owned = [path for path, _ in _declared(_catalog()["features"][feature])]
    importers = {file for module in _provided()[_distribution(specifier)] for file in _importers().get(module, ())}

    assert value in declared["choices"]
    assert importers, specifier
    assert all(_under(file, owned) for file in importers), sorted(importers)
    for file in importers:
        if _owning_condition(file) == f"{feature}.{option}={value}":
            continue
        assert not _provided()[_distribution(specifier)] & _imports_outright(REPO_ROOT / file), (
            f"{file} imports {specifier} without a guard, and a project that chose another value has it absent"
        )


def test_no_runtime_dependency_is_one_only_the_tests_import():
    """A distribution only the tests import is installed in production for nothing.

    `backend/Dockerfile` installs the runtime list with `--no-dev`, so that is the list that
    decides the image. A distribution nothing imports at all is left alone here: several are
    needed indirectly, through something that doesn't declare them.
    """
    runtime = _declared_distributions("runtime")
    application = _imported("src", "scripts", "migrations")
    tests = _imported("tests")

    only_tested = {
        name for name in runtime if _provided().get(name, frozenset()) & tests and not _provided()[name] & application
    }

    assert only_tested == set()


DEVELOPMENT_SCRIPT = "scripts/baseline.py"
"""The one script a project runs from its development environment rather than from the image."""


def test_no_dependency_the_application_imports_is_declared_for_development_only():
    """The other way round, where `uv export --no-dev` would leave an import with nothing behind it.

    The scripts are read too, because an operator runs them in the image: the first-run guide
    seeds a deployment with `docker compose exec api python -m scripts.setup_initial_data`, and
    the repairs, the usage prune and the account unlock are all run the same way. `baseline.py`
    is the exception, and the only one: it writes a project's first migration against a container
    it starts itself, which is a thing to do once, from a checkout.
    """
    development = _declared_distributions("dev") - _declared_distributions("runtime")
    application = _imported("src", "scripts", "migrations", skipping=(DEVELOPMENT_SCRIPT,))

    assert {name for name in development if _provided().get(name, frozenset()) & application} == set()


def test_the_dependency_readings_find_what_they_claim_to():
    """Both rules report what they found, so a reading that stopped working would pass quietly."""
    assert "fastapi" in _imported("src", "migrations")
    assert "pytest" in _imported("tests")
    assert _provided()["sqlalchemy"] == frozenset({"sqlalchemy"})
    assert "testcontainers" in _imported("scripts")
    assert "testcontainers" not in _imported("scripts", skipping=(DEVELOPMENT_SCRIPT,))
    assert "asyncio" in _imported("scripts", skipping=(DEVELOPMENT_SCRIPT,)), "the other scripts are still read"


@pytest.mark.parametrize("entry", sorted(_catalog()["blueprint"]["blueprint_only"]))
def test_every_blueprint_only_path_is_written_the_way_the_spec_reads_them(entry: str):
    """Spec 1.1: a trailing slash means the subtree, and without one it is a single file.

    `docs` rather than `docs/` would name one file nobody has, and the whole tree would
    reach projects.
    """
    assert not entry.startswith("/")
    assert ".." not in Path(entry).parts
    assert entry.endswith("/") == _is_tracked_dir(REPO_ROOT / entry)


@pytest.mark.parametrize("entry", sorted(_catalog()["blueprint"]["blueprint_only"]))
def test_every_blueprint_only_path_is_one_this_repo_has(entry: str):
    """A path that no longer exists keeps a file out of projects that nobody meant to keep out."""
    assert _is_tracked(REPO_ROOT / entry)


def _withheld(path: str) -> bool:
    """Whether `blueprint_only` keeps a project from receiving this path (spec 1.1 subtrees)."""
    return any(
        path == entry.rstrip("/") or (entry.endswith("/") and path.startswith(entry))
        for entry in _catalog()["blueprint"]["blueprint_only"]
    )


def _workspace_members() -> list[str]:
    with (REPO_ROOT / "pyproject.toml").open("rb") as handle:
        return list(tomllib.load(handle)["tool"]["uv"]["workspace"]["members"])


def _root_project_paths() -> list[str]:
    """The workspace members and the test paths the root `pyproject.toml` names."""
    root = _root_project()

    return [*root["tool"]["uv"]["workspace"]["members"], *root["tool"]["pytest"]["ini_options"]["testpaths"]]


def _unwrapped(pattern: str) -> str:
    """A pattern without the one group that wraps all of it, if there is one."""
    depth = 0
    for index, character in enumerate(pattern):
        depth += {"(": 1, ")": -1}.get(character, 0)
        if depth == 0:
            return pattern[1:-1] if pattern.startswith("(") and index == len(pattern) - 1 else pattern

    return pattern


def _alternatives(pattern: str) -> list[str]:
    """The top-level alternatives of an anchored pattern, outside a group that wraps it whole."""
    body = _unwrapped(pattern.removeprefix("^").removesuffix("$"))

    parts, depth, start = [], 0, 0
    for index, character in enumerate(body):
        depth += {"(": 1, "[": 1, ")": -1, "]": -1}.get(character, 0)
        if character == "|" and depth == 0:
            parts.append(body[start:index])
            start = index + 1

    return [*parts, body[start:]]


def _literal_head(pattern: str) -> str:
    """The characters a pattern matches literally before its first special one, unescaped."""
    head = re.match(r"(?:[^\\()\[\]{}|?*+.^$]|\\[./-])*", pattern)
    assert head is not None

    return re.sub(r"\\(.)", r"\1", head.group())


def _pattern_heads(pattern: str) -> list[str]:
    """The path each alternative of a pre-commit `files:` pattern starts with, through nested ones."""
    alternatives = _alternatives(pattern)
    if len(alternatives) > 1:
        return [head for alternative in alternatives for head in _pattern_heads(alternative)]

    return [_literal_head(alternatives[0]).rstrip("/")]


def _named_paths(patterns: list[str]) -> list[str]:
    """The paths the patterns name, refusing one whose head is empty: it would name nothing to check."""
    heads = [head for pattern in patterns for head in _pattern_heads(pattern)]
    assert all(heads), patterns

    return heads


def _hook_paths() -> list[str]:
    """The paths the pre-commit `files:` patterns name, one per alternative."""
    return _named_paths(re.findall(r"^\s*files: (\S+)$", (REPO_ROOT / ".pre-commit-config.yaml").read_text(), re.M))


@pytest.mark.parametrize(
    ("pattern", "heads"),
    [
        ("^docs/", ["docs"]),
        ("^backend/(src|scripts|migrations|tests)/", ["backend"]),
        (r"^(blueprint\.toml|fastro\.toml|backend/src/wiring/)", ["blueprint.toml", "fastro.toml", "backend/src/wiring"]),
        (r"^(a\.py)|(b/)$", ["a.py", "b"]),
        (r"^(a|(b\.py|c/))$", ["a", "b.py", "c"]),
        (r"^(a|b)/x", [""]),
    ],
)
def test_the_hook_reader_sees_every_path_a_pattern_names(pattern: str, heads: list[str]):
    """An alternation names one path per branch, and an escaped dot is part of the name."""
    assert _pattern_heads(pattern) == heads


def test_the_hook_reader_refuses_a_pattern_that_names_no_path():
    """A head of `""` is never withheld, so the rules that read it would pass over nothing."""
    with pytest.raises(AssertionError):
        _named_paths([r"^(a|b)/x"])


def _readme_references() -> list[str]:
    """The files the README's own markup points at, leaving out what it fetches over the network."""
    found = re.findall(r'src(?:set)?="([^"]+)"', (REPO_ROOT / "README.md").read_text())

    return [reference for reference in found if not reference.startswith("http")]


POINTS_AT = {
    "pyproject.toml": _root_project_paths,
    ".pre-commit-config.yaml": _hook_paths,
    "README.md": _readme_references,
}
"""Each root file that names paths, read the way that file spells them."""


@pytest.mark.parametrize("path", sorted(POINTS_AT))
def test_no_file_a_project_receives_points_at_one_it_does_not(path: str):
    """Either the pointer goes or the file does.

    A workspace member a project never receives is a project `uv sync` refuses; a test path is
    a pytest run that collects nothing; a lint pattern is a hook over nothing; an image is a
    hole where the cover was. The three root files are the blueprint's own, so they are the
    ones that go.
    """
    withheld = sorted(target for target in POINTS_AT[path]() if _withheld(target))

    assert not withheld or _withheld(path), (path, withheld)


WITHHELD_POINTERS = {
    "pyproject.toml": "blueprint/tests",
    ".pre-commit-config.yaml": "blueprint.toml",
    "README.md": "docs/assets",
}
"""What keeps each of the three out of a project, pinned so a reader of it can't go quiet."""


@pytest.mark.parametrize("path", sorted(POINTS_AT))
def test_each_file_still_names_the_path_that_keeps_it_out(path: str):
    """The reason each file is blueprint-only, rather than the fact of it.

    A format that moved on -- a renamed pre-commit key, an image moved out of `docs/` -- would
    leave the rule above with nothing to object to, and the file would ship. The root
    `pyproject.toml` is kept out by the blueprint's own tests, which its pytest config runs.
    """
    pointed = POINTS_AT[path]()

    assert any(target.startswith(WITHHELD_POINTERS[path]) for target in pointed), pointed


ROOT_PYPROJECT = REPO_ROOT / "pyproject.toml"
FASTRO_REPOSITORY = "https://github.com/benavlabs/fastro"
COMMIT = re.compile(r"^[0-9a-f]{40}$")


def _root_project() -> dict[str, Any]:
    with ROOT_PYPROJECT.open("rb") as handle:
        return tomllib.load(handle)


def test_the_backend_is_the_workspaces_one_member():
    """The old developer tool's package is gone."""
    assert _workspace_members() == ["backend"]


def test_the_repository_root_installs_fastro_for_its_own_checks():
    """fastro checks the blueprint, so the root project, which no project receives, carries it."""
    assert _withheld("pyproject.toml")
    assert "fastro" in {_distribution(specifier) for specifier in _root_project()["dependency-groups"]["dev"]}


def test_fastro_is_pinned_to_one_commit_of_its_repository():
    """Unreleased, so a commit is the only version a lock can hold steady."""
    source = _root_project()["tool"]["uv"]["sources"]["fastro"]

    assert source.keys() == {"git", "rev"}
    assert source["git"] == FASTRO_REPOSITORY
    assert COMMIT.match(source["rev"]), source["rev"]


def test_no_project_receives_the_fastro_pin():
    """A project gets `backend/pyproject.toml`, and its own checks run fastro through `uvx`."""
    with BACKEND_PYPROJECT.open("rb") as handle:
        backend = tomllib.load(handle)

    groups = [
        backend["project"].get("dependencies", []),
        *backend["project"].get("optional-dependencies", {}).values(),
        *backend.get("dependency-groups", {}).values(),
    ]

    assert "fastro" not in {_distribution(specifier) for group in groups for specifier in group}
    assert "fastro" not in backend.get("tool", {}).get("uv", {}).get("sources", {})


def _pre_commit_repositories(config: str | None = None) -> list[dict[str, Any]]:
    """Each `- repo:` entry of `.pre-commit-config.yaml`, parsed."""
    parsed = yaml.safe_load((REPO_ROOT / ".pre-commit-config.yaml").read_text() if config is None else config)
    repositories: list[dict[str, Any]] = parsed["repos"]

    return repositories


def _pre_commit_hooks(config: str | None = None) -> list[dict[str, Any]]:
    return [hook for repository in _pre_commit_repositories(config) for hook in repository["hooks"]]


def test_the_pre_commit_reader_reads_what_yaml_means_not_how_it_is_written():
    hooks = _pre_commit_hooks(
        "repos:\n"
        "  - repo: local\n"
        "    hooks:\n"
        '      - id: "commented"  # why\n'
        "        # a note\n"
        "        entry: run it  # how\n"
        "\n"
        "        stages: [ 'manual' ]\n"
        "      - id: listed\n"
        "        stages:\n"
        "          - manual  # first\n"
        "          - pre-push\n"
        "        pass_filenames: false\n"
    )

    assert hooks == [
        {"id": "commented", "entry": "run it", "stages": ["manual"]},
        {"id": "listed", "stages": ["manual", "pre-push"], "pass_filenames": False},
    ]


def _the_sync_check_hook() -> dict[str, Any]:
    hooks = [hook for hook in _pre_commit_hooks() if "fastro sync --check" in hook.get("entry", "")]
    assert len(hooks) == 1, hooks

    return hooks[0]


SYNC_CHECK_TRIGGERS_BY_NAME = {"blueprint.toml", "fastro.toml", "pyproject.toml", "uv.lock"}
"""The files the guides name as running the sync check; the wiring they name by what it is."""


def _path_spans(text: str) -> set[str]:
    """Each code span that reads as a path: no spaces, and a directory or an extension."""
    return {span for span in re.findall(r"`([^`]+)`", text) if re.fullmatch(r"[\w./-]+", span) and re.search(r"[/.]", span)}


def _assert_names_the_sync_check_triggers(text: str) -> None:
    assert _path_spans(text) == SYNC_CHECK_TRIGGERS_BY_NAME, _path_spans(text)
    for path in _path_spans(text):
        assert re.search(_the_sync_check_hook()["files"], path), path


def test_a_commit_runs_sync_check_on_the_whole_tree():
    """`sync --check` compares every wiring file, so the hook hands it no file names."""
    hook = _the_sync_check_hook()

    assert hook["entry"] == "uv run --no-sync fastro sync --check"
    assert hook["language"] == "system"
    assert hook["pass_filenames"] is False


def test_the_sync_check_hook_runs_at_every_commit():
    """Any key beyond these narrows when it runs: a stage, an exclusion, a file type."""
    assert _the_sync_check_hook().keys() == {"id", "name", "language", "entry", "pass_filenames", "files"}


@pytest.mark.parametrize("path", ["blueprint.toml", "fastro.toml", *(entry["path"] for entry in _catalog()["wiring"])])
def test_a_commit_that_touches_what_sync_compares_runs_sync_check(path: str):
    """The catalog, the selection and every file it generates, so a new wiring file can't slip by."""
    assert re.search(_the_sync_check_hook()["files"], path), path


@pytest.mark.parametrize("path", ["pyproject.toml", "uv.lock"])
def test_a_commit_that_moves_the_fastro_pin_runs_sync_check(path: str):
    """Another fastro can render the same catalog differently, so the files that pin it count too."""
    assert re.search(_the_sync_check_hook()["files"], path), path


def test_a_commit_that_touches_nothing_sync_compares_skips_sync_check():
    for path in (
        "backend/src/modules/user/models.py",
        "docs/backend/src/wiring/app.md",
        "backend/fastro.toml",
        "blueprint.toml.orig",
        "backend/pyproject.toml",
        "backend/uv.lock",
        "uv_lock",
        "pyproject_toml",
        "fastro_toml",
        "blueprint_toml",
    ):
        assert not re.search(_the_sync_check_hook()["files"], path), path


def _hook_repositories() -> dict[str, str]:
    """Each hook id in `.pre-commit-config.yaml`, with the repository it comes from."""
    return {hook["id"]: repository["repo"] for repository in _pre_commit_repositories() for hook in repository["hooks"]}


def _development_guide_pre_commit_section() -> str:
    guide = (REPO_ROOT / "docs" / "user-guide" / "development.md").read_text()

    return guide.split("## Pre-Commit", 1)[1].split("\n\n## ", 1)[0]


def _development_guide_hook_rows() -> dict[str, str]:
    """The guide's pre-commit table, each row keyed by each hook its first cell names, or by the cell if it names none."""
    rows = re.findall(r"^\| (?!Hook\b|-)(.+?) \| (.+) \|$", _development_guide_pre_commit_section(), re.M)

    named = [
        (name, cells)
        for names, cells in rows
        for name in [code.split()[0] for code in re.findall(r"`([^`]+)`", names)] or [names]
    ]
    assert len({name for name, _ in named}) == len(named), named

    return dict(named)


def test_the_development_guide_names_every_hook_a_commit_runs():
    assert _hook_repositories()
    assert set(_hook_repositories()) <= set(_development_guide_hook_rows())


def test_the_development_guide_names_no_hook_the_config_lacks():
    assert set(_development_guide_hook_rows()) <= set(_hook_repositories())


def test_the_development_guide_says_which_hooks_are_local():
    rows = _development_guide_hook_rows()
    local = {hook for hook, repository in _hook_repositories().items() if repository == "local"}

    assert local
    assert {hook for hook, cells in rows.items() if cells.startswith("local")} == local


def test_the_development_guide_says_which_hooks_run_only_when_asked_for():
    manual = {hook["id"] for hook in _pre_commit_hooks() if hook.get("stages") == ["manual"]}

    assert manual
    assert {hook for hook, cells in _development_guide_hook_rows().items() if "manual stage" in cells} == manual


def test_the_development_guide_gives_the_command_the_sync_check_hook_runs():
    row = _development_guide_hook_rows()[_the_sync_check_hook()["id"]]
    entry = f"`{_the_sync_check_hook()['entry']}`"

    assert entry in row
    _assert_names_the_sync_check_triggers(row)
    assert "wiring" in row.replace(entry, "")


def _hook_shell_line(hook: dict[str, str]) -> str:
    """What a hook runs, without the `bash -c` that lets a local hook change directory first."""
    found = re.fullmatch(r"bash -c '(.+)'", hook["entry"])

    return found[1] if found else hook["entry"]


def _ci_runs_command(command: str) -> bool:
    """Whether a CI step runs this command, alone or on paths after it."""
    return any(re.fullmatch(rf"(?:uv run --no-sync )?{re.escape(command)}(?: [^-\s]\S*)*", run) for run in _workflow_runs())


def _names_ci(row: str) -> bool:
    """Whether a row of the development guide's hook table says what CI runs."""
    return re.search(r"\bCI\b", row) is not None


def _ci_runs_hook(hook: dict[str, str]) -> bool:
    """Whether a CI step runs a local hook's command, as it is or on every path instead of the ones it names."""
    line = _hook_shell_line(hook)

    return line in _workflow_runs() or _without_trailing_paths(line) in _workflow_runs()


def _names_a_path(word: str) -> bool:
    return any(mark in word for mark in "/.") and all(char.isalnum() or char in "_./-" for char in word)


def _without_trailing_paths(line: str) -> str:
    """The line with the space-separated paths it ends in dropped: a word of letters, digits,
    ``_``, ``.``, ``/`` and ``-`` that holds a ``/`` or a ``.``. The first word always stays, and so
    does a newline the line ends in."""
    body, newline = (line[:-1], "\n") if line.endswith("\n") else (line, "")
    words = body.split(" ")
    while len(words) > 1 and _names_a_path(words[-1]):
        words.pop()

    return " ".join(words) + newline


@pytest.mark.parametrize(
    ("line", "kept"),
    [
        ("uv run --no-sync ruff check src/app.py tests/x.py", "uv run --no-sync ruff check"),
        ("cd backend && mypy src/a.py", "cd backend && mypy"),
        ("ruff format --check .", "ruff format --check"),
        ("mypy src tests", "mypy src tests"),
        ("pytest -q", "pytest -q"),
        ("x.py", "x.py"),
        ("ruff --config=a.toml", "ruff --config=a.toml"),
        ("run a/b  c/d", "run a/b "),
        ("mypy src/ ", "mypy src/ "),
        ("run src/a.py tests", "run src/a.py tests"),
        ("run ../up", "run"),
        ("run tests/unit_2/my-file.py", "run"),
        ("x a/b\n", "x\n"),
    ],
)
def test_a_hook_line_drops_the_paths_it_ends_in(line: str, kept: str):
    assert _without_trailing_paths(line) == kept


def test_a_long_line_of_dots_is_read_at_once():
    line = "run" + " .." * 100_000 + " !"
    started = time.perf_counter()

    assert _without_trailing_paths(line) == line
    assert _without_trailing_paths(line[:-2]) == "run"
    assert time.perf_counter() - started < 1


def test_the_hooks_the_development_guide_says_ci_runs_run_what_ci_runs():
    rows = _development_guide_hook_rows()
    claimed = [hook for hook in _pre_commit_hooks() if _names_ci(rows[hook["id"]])]

    assert claimed
    for hook in claimed:
        if "entry" in hook:
            assert _ci_runs_hook(hook), hook["id"]
        else:
            commands = [span for span in re.findall(r"`([^`]+)`", rows[hook["id"]]) if " " in span]
            assert any(command.startswith(hook["id"].replace("-", " ")) for command in commands), hook["id"]
            for command in commands:
                assert _ci_runs_command(command), command


def test_the_hooks_the_development_guide_leaves_ci_out_of_are_no_ci_step():
    rows = _development_guide_hook_rows()
    unclaimed = [hook for hook in _pre_commit_hooks() if not _names_ci(rows[hook["id"]])]

    assert unclaimed
    for hook in unclaimed:
        if "entry" in hook:
            assert not _ci_runs_hook(hook), hook["id"]
        else:
            for name in {hook["id"], hook["id"].replace("-", " ")}:
                assert not any(re.search(rf"\b{re.escape(name)}\b", run) for run in _workflow_runs()), name


def test_the_development_guide_gives_the_command_each_manual_hook_runs_and_where():
    manual = [hook for hook in _pre_commit_hooks() if hook.get("stages") == ["manual"]]

    assert manual
    for hook in manual:
        found = re.fullmatch(r"cd (\S+) && (.+)", _hook_shell_line(hook))
        assert found, hook["id"]
        directory, command = found.groups()
        row = _development_guide_hook_rows()[hook["id"]]
        assert f"`{command}`" in row, row
        assert f"`{directory}/`" in row, row


def _development_guide_pre_commit_prose() -> str:
    """The development guide's Pre-Commit section, past its hook table."""
    return _development_guide_pre_commit_section().rsplit("\n|", 1)[1].split("\n", 1)[1]


def test_some_unit_tests_start_containers_through_testcontainers():
    """The development guide's claim; `blueprint/tests/test_pre_commit.py` runs the hook without Docker to show they skip."""
    unit = REPO_ROOT / "backend" / "tests" / "unit"

    assert "`testcontainers`" in _development_guide_pre_commit_prose()
    assert any(
        isinstance(node, ast.ImportFrom) and re.fullmatch(r"testcontainers(?:\..+)?", node.module or "")
        for path in _tracked(unit)
        if path != Path(__file__).resolve()
        for node in ast.walk(ast.parse(path.read_text()))
    )


def test_docker_counts_as_not_running_when_its_client_cannot_connect(monkeypatch):
    monkeypatch.setenv("DOCKER_HOST", "tcp://127.0.0.1:1")
    monkeypatch.setattr("testcontainers.core.config.testcontainers_config.tc_properties", {})

    assert is_docker_running() is False


def test_the_project_puts_an_attribute_docstring_under_a_module_level_name():
    """Why the development guide leaves `check-docstring-first` out."""
    documented = [
        path
        for path in _tracked(REPO_ROOT / "backend")
        if path.relative_to(REPO_ROOT / "backend").parts[0][0] in "st"
        and len(path.relative_to(REPO_ROOT / "backend").parts) > 1
        if any(
            isinstance(name, ast.Assign | ast.AnnAssign)
            and isinstance(docstring, ast.Expr)
            and isinstance(docstring.value, ast.Constant)
            and isinstance(docstring.value.value, str)
            for name, docstring in itertools.pairwise(ast.parse(path.read_text()).body)
        )
    ]

    assert any(path.is_relative_to(REPO_ROOT / "backend" / "src") for path in documented), documented
    assert "`check-docstring-first`" in _development_guide_pre_commit_prose()


def test_the_hooks_the_development_guide_leaves_out_are_not_in_the_config():
    left_out = {"mdformat", "blacken-docs", "check-docstring-first"}
    named = set(re.findall(r"`([\w-]+)`", _development_guide_pre_commit_prose()))

    assert left_out <= named
    assert not left_out & set(_hook_repositories())
    assert "ruff-format" in named & set(_hook_repositories())


def test_the_extra_the_development_guide_names_installs_pre_commit():
    prose = _development_guide_pre_commit_prose()
    extra = re.search(r"`pre-commit` ships in the `([\w-]+)` extra, so `(uv sync[^`]*)`", prose)
    assert extra, prose

    assert {"--all-packages", "--all-extras"} <= set(extra[2].split())
    assert any(
        re.match(r"pre-commit(?![\w.-])", requirement)
        for member in tomllib.loads((REPO_ROOT / "pyproject.toml").read_text())["tool"]["uv"]["workspace"]["members"]
        for requirement in tomllib.loads((REPO_ROOT / member / "pyproject.toml").read_text())["project"]
        .get("optional-dependencies", {})
        .get(extra[1], [])
    )


def test_each_hook_the_development_guide_runs_by_name_is_in_the_config_at_the_stage_it_gives():
    runs = re.findall(r"pre-commit run (\w[\w-]*)(.*)$", _development_guide_pre_commit_prose(), re.M)
    hooks = {hook["id"]: hook for hook in _pre_commit_hooks()}

    assert runs
    for hook, flags in runs:
        assert hook in hooks, hook
        stage = re.search(r"--hook-stage (\w+)", flags)
        assert hooks[hook].get("stages", ["pre-commit"]) == [stage[1] if stage else "pre-commit"], hook


def test_each_pre_commit_command_the_development_guide_gives_takes_the_flags_it_passes():
    prose = _development_guide_pre_commit_prose()
    commands = re.findall(r"^uv run --no-sync pre-commit (\w+)(.*)$", prose, re.M)

    assert commands
    for fence in re.findall(r"^```bash\n(.*?)^```$", prose, re.M | re.S):
        for line in fence.splitlines():
            assert "pre-commit" not in line or line.startswith("uv run --no-sync pre-commit "), line
    for subcommand, arguments in commands:
        usage = subprocess.run(
            [sys.executable, "-m", "pre_commit", subcommand, "--help"], capture_output=True, text=True, check=False
        )
        assert usage.returncode == 0, subcommand
        for flag in re.findall(r"(?<!\S)(--?[\w-]+)", arguments):
            assert re.search(rf"(?<![\w-]){re.escape(flag)}(?![\w-])", usage.stdout), (subcommand, flag)


def _workflow_runs(workflows: Iterable[str] | None = None) -> list[str]:
    """Each line every `run:` in the repository's own CI runs, a block's line by line."""
    if workflows is None:
        workflows = [
            workflow.read_text() for workflow in _tracked(REPO_ROOT / ".github" / "workflows", "*.yml", recursive=False)
        ]

    return [
        line.strip()
        for workflow in workflows
        for job in yaml.safe_load(workflow)["jobs"].values()
        for step in job.get("steps", [])
        for line in str(step.get("run", "")).splitlines()
        if line.strip()
    ]


def test_the_workflow_reader_reads_every_run_and_a_block_line_by_line():
    workflow = (
        "jobs:\n"
        "  a:\n"
        "    steps:\n"
        "      - run: uv sync  # first\n"
        "      - name: named\n"
        "        run: 'uv run --no-sync pytest'\n"
        "      - name: block\n"
        "        run: |\n"
        "          echo one\n"
        "\n"
        "          if true; then\n"
        "            echo two\n"
        "          fi\n"
        "  b:\n"
        "    uses: ./.github/workflows/other.yml\n"
    )

    assert _workflow_runs([workflow]) == ["uv sync", "uv run --no-sync pytest", "echo one", "if true; then", "echo two", "fi"]


def test_ci_type_checks_the_blueprint_tests_it_runs():
    """A test file nobody type-checks can drift from the code it reads, and only fail when it runs."""
    runs = _workflow_runs()
    tested = {
        argument.rstrip("/")
        for run in runs
        if run.startswith("uv run --no-sync pytest ")
        for argument in run.split()[4:]
        if argument.startswith("blueprint/")
    }
    checked = [run.split()[4:] for run in runs if run.startswith("uv run --no-sync mypy ")]

    assert tested
    for directory in tested:
        assert any(
            directory == path.rstrip("/") or directory.startswith(path.rstrip("/") + "/") for paths in checked for path in paths
        ), directory


def _defaults_blocks(workflow: str) -> list[str]:
    """Each `defaults:` block of a workflow, at any level, with its value written on the same line or below it."""
    lines = workflow.splitlines()
    blocks = []
    for index, line in enumerate(lines):
        found = re.match(r"^( *)defaults:(.*)$", line)
        if found is None:
            continue

        block = [found.group(2)]
        for following in lines[index + 1 :]:
            if following.strip() and len(following) - len(following.lstrip()) <= len(found.group(1)):
                break
            block.append(following)
        blocks.append("\n".join(block))

    return blocks


@pytest.mark.parametrize(
    "workflow",
    [
        "defaults:\n  run:\n    working-directory: backend\njobs:\n",
        "jobs:\n  lint:\n    defaults:\n      run:\n        shell: bash\n        working-directory: backend\n    steps:\n",
        "jobs:\n  lint:\n    defaults: {run: {working-directory: backend}}\n",
    ],
)
def test_the_defaults_reader_sees_a_working_directory_however_it_is_written(workflow: str):
    assert any("working-directory" in block for block in _defaults_blocks(workflow))


def test_the_defaults_reader_stops_at_the_end_of_its_block():
    workflow = "defaults:\n  run:\n    shell: bash\njobs:\n  lint:\n    steps:\n      - working-directory: backend\n"

    assert not any("working-directory" in block for block in _defaults_blocks(workflow))


SYNC_THAT_KEEPS_THE_DEV_GROUP = {"uv", "sync", "--all-packages", "--all-extras", "--locked", "--python", "3.11"}
"""The words a sync may use and still install the root dev group, where fastro is."""


@pytest.mark.parametrize("command", ["fastro sync --check", "fastro blueprint lint"])
def test_ci_runs_fastros_checks_where_fastro_is_installed(command: str):
    """From the repository root, the project that declares fastro, never after a `cd`, and always gating the job."""
    assert [run for run in _workflow_runs() if command in run] == [f"uv run --no-sync {command}"]

    for workflow in _tracked(REPO_ROOT / ".github" / "workflows", "*.yml", recursive=False):
        text = workflow.read_text()
        steps = [step for step in re.split(r"\n(?= +- )", text) if command in step]
        if steps:
            assert not any("working-directory" in block for block in _defaults_blocks(text)), workflow.name
            for step in steps:
                assert set(re.findall(r"^\s*(?:- )?([\w-]+):", step, re.M)) == {"name", "run"}, step

            syncs = re.findall(r"^\s+run: (uv sync\b.*)$", text, re.M)
            assert syncs, workflow.name
            for sync in syncs:
                assert set(sync.split()) <= SYNC_THAT_KEEPS_THE_DEV_GROUP, sync


CONTRIBUTING = REPO_ROOT / "CONTRIBUTING.md"

UV_THAT_WROTE_THE_LOCK = {5: "0.13.8"}
"""The uv release this repository's lock was first written with at each revision, not the first release that writes it."""


def _contributing_syncs() -> list[str]:
    """Each sync the guide gives as a command on its own line, not a sync it names inline in prose."""
    return re.findall(r"^\s*(?:\$\s+)?(uv sync\b.*)$", CONTRIBUTING.read_text(), re.M)


def _imported_modules(module: str, source: str) -> set[str]:
    """Each module a file imports, and each name it imports from one, with relative imports resolved."""
    package = module.split(".")[:-1]
    imported: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            anchor = package[: len(package) - node.level + 1] if node.level else []
            base = ".".join([*anchor, *filter(None, [node.module])])
            imported.add(base)
            imported.update(f"{base}.{alias.name}" for alias in node.names)

    return imported


def test_every_test_that_reads_the_docs_or_imports_a_withheld_test_stays_in_the_blueprint():
    backend = REPO_ROOT / "backend"
    files = {".".join(path.relative_to(backend).with_suffix("").parts): path for path in _tracked(backend / "tests")}
    withheld = {module for module, path in files.items() if _withheld(str(path.relative_to(REPO_ROOT)))}
    reading = []
    for module, path in sorted(files.items()):
        source = path.read_text()
        if re.search(r"""(?:["']|\}/|\.\./)docs["'/]""", source) or withheld & _imported_modules(module, source):
            reading.append(path)

    assert {f"test_docs_{name}.py" for name in ("imports", "recipes", "scripts", "wiring")} <= {path.name for path in reading}
    for path in reading:
        assert _withheld(str(path.relative_to(REPO_ROOT))), (
            f"{path.relative_to(REPO_ROOT)} reads the docs, which describe every feature, or imports a blueprint-only test, "
            "so it assumes the full repo: list it under [blueprint].blueprint_only in blueprint.toml"
        )


def test_the_contributing_guide_is_the_blueprint_s_own():
    assert _withheld("CONTRIBUTING.md")


def test_the_sync_the_contributing_guide_gives_installs_fastro():
    """Every sync it gives keeps the root dev group, where fastro is."""
    assert _contributing_syncs()
    for sync in _contributing_syncs():
        assert set(sync.split()) <= SYNC_THAT_KEEPS_THE_DEV_GROUP, sync


def test_the_readme_s_quickstart_sync_installs_fastro():
    """Every sync the README gives keeps the root dev group, and says it brings fastro in."""
    syncs = re.findall(r"^\s*(?:\$\s+)?(uv sync\b[^#\n]*)(#.*)?$", (REPO_ROOT / "README.md").read_text(), re.M)

    assert syncs
    for sync, note in syncs:
        assert set(sync.split()) <= SYNC_THAT_KEEPS_THE_DEV_GROUP, sync
        assert re.search(r"\bfastro\b", note), note


def test_the_contributing_guide_names_the_group_that_pins_fastro():
    groups = [
        group
        for group, specifiers in _root_project()["dependency-groups"].items()
        if "fastro" in {_distribution(specifier) for specifier in specifiers}
    ]

    assert len(groups) == 1, groups
    assert f"`{groups[0]}`" in CONTRIBUTING.read_text()


def test_the_contributing_guide_names_the_uv_that_wrote_the_lock():
    """A uv older than the one that wrote the lock can write it back at an older revision, so the guide names that release."""
    with (REPO_ROOT / "uv.lock").open("rb") as handle:
        revision = tomllib.load(handle)["revision"]
    assert revision in UV_THAT_WROTE_THE_LOCK, f"add the uv that wrote lock revision {revision}, and name it in CONTRIBUTING.md"

    text = CONTRIBUTING.read_text()
    assert re.search(rf"\brevision\s+{revision}\b", text)
    assert set(re.findall(r"\buv\s+(\d+\.\d+\.\d+)", text)) == {UV_THAT_WROTE_THE_LOCK[revision]}
    assert re.search(rf"uv\s+{re.escape(UV_THAT_WROTE_THE_LOCK[revision])}\s+or\s+(?:newer|later)\b", text)


def _the_guide_s_sync_check_sentence() -> str:
    hook = f"`{_the_sync_check_hook()['entry']}`"
    sentences = [sentence for sentence in re.split(r"(?<=\.)\s+", CONTRIBUTING.read_text()) if hook in sentence]
    assert len(sentences) == 1, sentences

    return sentences[0]


def test_the_contributing_guide_names_the_check_a_commit_runs():
    """`blueprint/tests/test_fastro.py::test_plain_sync_regenerates_what_the_check_compares` proves what it does."""
    assert _the_guide_s_sync_check_sentence()


def test_the_contributing_guide_names_every_file_that_runs_the_check():
    """The catalog, the selection and the pin by name, and the wiring, each one the hook runs on."""
    sentence = _the_guide_s_sync_check_sentence()

    _assert_names_the_sync_check_triggers(sentence)
    assert "wiring" in sentence.split(f"`{_the_sync_check_hook()['entry']}`")[0]


def test_the_check_runs_on_no_file_the_contributing_guide_leaves_out():
    """Each trigger is a file the guide names or a wiring file, so a new one fails until the guide names it."""
    named = _path_spans(_the_guide_s_sync_check_sentence())
    wiring = [entry["path"] for entry in _catalog()["wiring"]]

    for alternative in _alternatives(_the_sync_check_hook()["files"]):
        assert re.sub(r"\\(.)", r"\1", alternative) in named or any(re.fullmatch(alternative, path) for path in wiring), (
            alternative
        )


def test_the_contributing_guide_names_the_command_that_fixes_a_failed_check():
    """`blueprint/tests/test_fastro.py::test_plain_sync_regenerates_what_the_check_compares` proves what it does."""
    assert "`uv run --no-sync fastro sync`" in CONTRIBUTING.read_text()


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
    """A test that reaches for `docs/` or `blueprint/` is a test no project can run.

    `test_baseline.py` read the migrations guide, a file a project never receives. Only the
    subtree entries are compared, because a root file's name is ambiguous: a shipped test naming
    `pyproject.toml` means the one under `backend/`.
    """
    trees = [entry for entry in _catalog()["blueprint"]["blueprint_only"] if entry.endswith("/")]
    reaching = {}
    for module in _tracked(REPO_ROOT / "backend" / "tests"):
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
    """The catalog and the docs belong to the blueprint only."""
    listed = set(_catalog()["blueprint"]["blueprint_only"])

    assert {"blueprint/", "blueprint.toml", "fastro.toml", "docs/"} <= listed
    assert "backend/tests/unit/test_blueprint_catalog.py" in listed


def test_the_docs_reading_tests_stay_in_the_blueprint():
    """They read `docs/`, which projects don't get, so they would fail in one."""
    listed = set(_catalog()["blueprint"]["blueprint_only"])

    for name in ("test_docs_imports", "test_docs_recipes", "test_docs_scripts", "test_docs_wiring", "test_image_contents"):
        assert f"backend/tests/unit/{name}.py" in listed


@pytest.mark.parametrize("name", sorted(_catalog()["presets"]) + sorted(_catalog()["verify"]["sets"]))
def test_every_preset_and_verify_set_is_named_the_way_the_spec_allows(name: str):
    """Spec 1.2: a name here is lower case and may carry a hyphen, so `accounts-only` reads as one."""
    assert SET_NAME.match(name)


def test_every_preset_is_closed_under_what_its_features_require():
    """A preset that names tier_limits without tiers would generate a project that can't import."""
    for name, features in _catalog()["presets"].items():
        assert _closed(features) == set(features), f"{name} is missing what its features require"


def test_the_presets_name_features_this_repository_has():
    known = set(_catalog()["features"])

    for name, features in _catalog()["presets"].items():
        assert set(features) <= known, name
        for feature in features:
            assert FEATURE_NAME.match(feature)


def test_full_is_every_feature():
    assert sorted(_catalog()["presets"]["full"]) == sorted(_catalog()["features"])


ONE_OF_EACH = {"root_routers", "docs_guard", "email_sender", "cache_decorator", "scope_fingerprint"}
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

    Read with ``ast`` rather than by matching text: names from one module share a statement,
    and a long one wraps over several lines, and neither shape contains the single-name line a
    substring check would look for.
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
    if not _is_tracked_file(path):
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


@pytest.mark.parametrize("entry", _catalog()["core"]["contributes"]["critical_readiness"])
def test_every_core_contribution_names_something_that_exists(entry: str):
    """Spec 1.4: the attribute has to be defined at the module's top level."""
    module, attribute, _ = _ref(entry)

    assert _defines(module, attribute), entry


def test_the_import_reader_sees_a_name_that_shares_a_statement():
    """Two names from one module in one statement, whose second name no line contains alone."""
    bindings = _bindings("from ..infrastructure.auth.health import limiter_readiness, sessions_readiness\n")

    assert ("..infrastructure.auth.health", "limiter_readiness", "limiter_readiness") in bindings
    assert ("..infrastructure.auth.health", "sessions_readiness", "sessions_readiness") in bindings


def test_the_import_reader_sees_a_name_in_a_wrapped_import():
    """An import written over several lines, so no single line holds it."""
    bindings = _bindings("from ..infrastructure.composition import (\n    PermissionSource,\n    ReadinessCheck,\n)\n")

    assert ("..infrastructure.composition", "ReadinessCheck", "ReadinessCheck") in bindings


GENERATED_BY_WIRING = "backend/src/wiring/admin.py"
"""Written by a `[[wiring]]` entry for the admin feature, so no feature's paths declare it."""


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
        if condition is None or _true(condition, chosen)
    }


def _owning_condition(relative: str) -> str | None:
    """The condition the declaration that owns this path keeps it under: the longest declared path
    that matches wins (spec 1.1), and a path nothing declares is the core's, kept always."""
    owning = [
        (path, condition)
        for feature in _catalog()["features"].values()
        for path, condition in _declared(feature)
        if relative == path or relative.startswith(f"{path}/")
    ]

    return max(owning, key=lambda declared: len(declared[0]))[1] if owning else None


def _declared_by_an_option_alone() -> list[tuple[str, str]]:
    """Each distribution only an option's choice declares, with that choice as a condition."""
    elsewhere = set(_catalog()["blueprint"]["dependencies"]["runtime"])
    for feature in _catalog()["features"].values():
        elsewhere.update(feature.get("dependencies", ()))
        for block in feature.get("when", ()):
            elsewhere.update(block.get("dependencies", ()))
    elsewhere_named = {_distribution(specifier) for specifier in elsewhere}

    return sorted(
        (_distribution(specifier), f"{name}.{option}={choice}")
        for name, feature in _catalog()["features"].items()
        for option, declared in feature.get("options", {}).items()
        for choice, specifiers in declared.get("dependencies", {}).items()
        for specifier in specifiers
        if _distribution(specifier) not in elsewhere_named
    )


@pytest.mark.parametrize(("distribution", "condition"), _declared_by_an_option_alone())
def test_a_module_that_imports_what_one_choice_installs_ships_only_with_that_choice(distribution: str, condition: str):
    """A project that chose otherwise doesn't install it, so the module would fail to import there
    and `blueprint verify` refuses the build: `cache.backend=redis` leaves `aiomcache` out."""
    modules = _provided()[distribution]
    root = REPO_ROOT / _catalog()["blueprint"]["python_root"]
    importing = [
        path.relative_to(REPO_ROOT).as_posix()
        for path in _tracked(root)
        if any(module.split(".")[0] in modules for module in _module_imports(path))
    ]

    assert importing
    assert {path: _owning_condition(path) for path in importing} == dict.fromkeys(importing, condition)


@pytest.mark.parametrize(
    ("path", "kept_with"),
    [
        ("backend/src/modules/user/admin.py", {"accounts", "admin"}),
        ("backend/src/modules/api_keys/tasks.py", {"accounts", "api_keys", "taskiq"}),
        ("backend/src/modules/api_keys/service.py", {"accounts", "api_keys"}),
        ("backend/src/infrastructure/taskiq/worker.py", {"taskiq"}),
        ("backend/src/infrastructure/taskiq/email.py", {"accounts", "taskiq"}),
        ("backend/tests/unit/infrastructure/taskiq/test_email.py", {"accounts", "taskiq"}),
        ("backend/src/modules/tier/admin.py", {"tiers", "admin"}),
        ("backend/tests/unit/modules/tier/test_admin.py", {"tiers", "admin"}),
        ("backend/src/modules/role/admin.py", {"rbac", "admin"}),
        ("backend/tests/unit/modules/role/test_admin.py", {"rbac", "admin"}),
        ("backend/tests/unit/modules/user/test_admin.py", {"accounts", "admin"}),
        ("backend/tests/unit/modules/api_keys/test_tasks.py", {"api_keys", "taskiq"}),
        ("backend/tests/integration/api_keys_rbac/test_effective_permissions.py", {"api_keys", "rbac"}),
        ("backend/tests/integration/api_keys_ratelimit/test_invalid_keys.py", {"api_keys", "ratelimit"}),
        ("backend/tests/integration/api_keys_tiers/test_reading_another_account.py", {"api_keys", "tier_limits"}),
        ("backend/tests/unit/infrastructure/cache/test_scoped_callers.py", {"cache", "accounts"}),
        ("backend/tests/integration/tier_limits/test_cached_listing.py", {"tier_limits", "cache"}),
    ],
)
def test_a_file_is_kept_exactly_where_its_features_are(path: str, kept_with: set[str]):
    """A file one feature brings into another's package is kept only when every feature it
    needs is selected, and leaves when any one of them is missing."""
    features = _catalog()["features"]
    declared = {declared for feature in features.values() for declared, _ in _declared(feature)}

    for chosen in _selections():
        kept_paths = _kept_by_the_catalog(features, chosen)
        kept = _under(path, kept_paths) and not _under(path, _removed_for(features, chosen))
        assert kept is (kept_with <= chosen), sorted(chosen)
        if path in declared:
            assert (path in kept_paths) is (kept_with <= chosen), sorted(chosen)


@pytest.mark.parametrize(
    ("condition", "chosen", "held"),
    [
        ("cache.backend=redis", {"cache"}, True),
        ("cache.backend=redis", set(), False),
        ("cache.backend=memcached", {"cache"}, False),
        ("cache.backend=memcached", {"cache", "cache.backend=memcached"}, True),
        ("cache.backend=redis", {"cache", "cache.backend=memcached"}, False),
        ("cache.backend=memcached", {"cache.backend=memcached"}, False),
        ("not cache.backend=memcached", {"cache"}, True),
    ],
)
def test_an_option_atom_holds_where_its_feature_is_selected_with_that_value(condition: str, chosen: set[str], held: bool):
    """Spec 1.3: the feature selected and its option equal to the value, the default when the
    selection doesn't choose one."""
    assert _true(condition, chosen) is held


@pytest.mark.parametrize(
    "path",
    [
        "backend/src/infrastructure/cache/backends/memcached.py",
        "backend/tests/unit/infrastructure/cache/backends/test_memcached.py",
    ],
)
def test_the_memcached_backend_is_kept_only_where_memcached_is_chosen(path: str):
    features = _catalog()["features"]

    for chosen, kept in [
        ({"cache", "cache.backend=memcached"}, True),
        ({"cache"}, False),
        ({"cache", "cache.backend=redis"}, False),
        ({"cache.backend=memcached"}, False),
    ]:
        removed = _removed_for(features, chosen)
        assert (_under(path, _kept_by_the_catalog(features, chosen)) and not _under(path, removed)) is kept, sorted(chosen)


def test_the_caching_page_says_where_the_memcached_backend_comes_from():
    whens = {block["if"]: block["paths"] for block in _catalog()["features"]["cache"]["when"]}
    page = (REPO_ROOT / "docs" / "user-guide" / "caching" / "index.md").read_text()

    chosen = _catalog()["features"]["cache"]["options"]["backend"]["dependencies"]["memcached"]

    assert "backend/src/infrastructure/cache/backends/memcached.py" in whens["cache.backend=memcached"]
    assert any(_distribution(specifier) == "aiomcache" for specifier in chosen)
    assert "`cache.backend=memcached` brings `aiomcache` and `infrastructure/cache/backends/memcached.py`" in " ".join(
        page.split()
    )


def _local_names(point: str, chosen: set[str]) -> list[str]:
    return [_ref(entry["ref"])[2] for entry in _contributed(_catalog(), point, chosen)]


def test_a_project_with_a_worker_queues_its_mail_and_one_without_hands_it_over():
    """No selection waits for a mail server: the fallback hands the delivery over."""
    fallback = next(slot for entry in _entries() for slot in entry["slots"] if slot.get("point") == "email_sender")

    assert fallback["fallback"] == "HandingOverSender(build_sender())"
    for chosen in _selections():
        expected = ["queued_sender"] if {"accounts", "taskiq"} <= chosen else []
        assert _local_names("email_sender", chosen) == expected, sorted(chosen)


def test_a_project_with_accounts_wires_the_scope_fingerprint_and_one_without_wires_none():
    """Accounts contributes it, and the cache imports nothing of accounts to read it."""
    fallback = next(slot for entry in _entries() for slot in entry["slots"] if slot.get("point") == "scope_fingerprint")

    assert fallback["fallback"] == "None"
    for chosen in _selections():
        expected = ["scope_fingerprint"] if "accounts" in chosen else []
        assert _local_names("scope_fingerprint", chosen) == expected, sorted(chosen)


def test_a_project_with_tiers_gives_a_new_account_the_default_tier_and_one_without_sets_nothing():
    for chosen in _selections():
        expected = ["default_tier"] if "tiers" in chosen else []
        assert _local_names("new_account_fields", chosen) == expected, sorted(chosen)


def test_a_project_drains_what_it_handed_over_with_the_worker_or_on_its_own():
    """Accounts hands its mail over, and drains it once: in the worker's lifecycle where there is
    one, and in the handover's own where there isn't."""
    for chosen in _selections():
        names = _local_names("lifecycles", chosen)

        assert ("taskiq_lifecycle" in names) is ("taskiq" in chosen), sorted(chosen)
        assert ("handover_lifecycle" in names) is ("accounts" in chosen and "taskiq" not in chosen), sorted(chosen)


def _closed(chosen: Iterable[str]) -> set[str]:
    """A selection with everything its features require, and what that requires in turn."""
    features = _catalog()["features"]
    selection = set(chosen)
    while missing := {required for name in selection for required in features[name].get("requires", ())} - selection:
        selection |= missing

    return selection


def _selections() -> list[set[str]]:
    """Every selection a project could carry: each subset of the features, closed under requires."""
    closed: list[set[str]] = []
    for size in range(len(_catalog()["features"]) + 1):
        for combination in itertools.combinations(_catalog()["features"], size):
            selection = _closed(combination)
            if selection not in closed:
                closed.append(selection)

    return closed


def test_a_project_can_carry_164_selections():
    """The rules below that run over every selection have that many to run over."""
    assert len(_selections()) == 164


@pytest.mark.parametrize("name", sorted(_catalog()["features"]))
def test_every_feature_is_declared_the_way_the_spec_asks(name: str):
    """Spec 2.4: a one-line summary, and the heading the checklist groups it under."""
    feature = _catalog()["features"][name]

    assert FEATURE_NAME.match(name)
    assert feature["summary"].strip() == feature["summary"]
    assert "\n" not in feature["summary"]
    assert feature["group"] in {"Accounts", "Operations"}


@pytest.mark.parametrize(
    ("name", "condition"),
    sorted((name, block["if"]) for name, feature in _catalog()["features"].items() for block in feature.get("when", ())),
)
def test_every_condition_names_a_feature_this_repository_has(name: str, condition: str):
    """Spec 1.3: an unknown name is an error rather than something that reads as false. An option
    atom names one of the feature's options and one of its choices."""
    if "=" in condition:
        feature, _, rest = condition.partition(".")
        option, _, value = rest.partition("=")
        assert value in _catalog()["features"][feature]["options"][option]["choices"]
    else:
        assert condition in _catalog()["features"]
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
    assert _is_tracked(REPO_ROOT / entry)


@pytest.mark.parametrize("name", sorted(_catalog()["features"]))
def test_a_directory_is_spelled_as_a_subtree_and_a_file_is_not(name: str):
    """Spec 1.1: `src/modules/user` without the slash would name one file nobody has."""
    for path in _catalog()["features"][name].get("paths", ()):
        assert path.endswith("/") == _is_tracked_dir(REPO_ROOT / path), path

    for block in _catalog()["features"][name].get("when", ()):
        for path in block.get("paths", ()):
            assert path.endswith("/") == _is_tracked_dir(REPO_ROOT / path), path


def test_no_path_is_declared_twice():
    """Spec 1.1: two declarations of the identical path are 'owned twice'."""
    declared = [path for feature in _catalog()["features"].values() for path, _ in _declared(feature)]

    assert sorted(declared) == sorted(set(declared))


def test_the_generated_wiring_file_belongs_to_no_feature():
    """It is written by `[[wiring]]`, which leaves it out of a project rather than deleting it."""
    declared = {path for feature in _catalog()["features"].values() for path, _ in _declared(feature)}

    assert GENERATED_BY_WIRING in [entry["path"] for entry in _entries()]
    assert GENERATED_BY_WIRING not in declared


def test_the_app_the_verification_imports_is_this_project_s_own():
    """Spec 2.2: a dotted module whose first part is `import_root`, and whose file this repository
    has. Without it `blueprint verify` skips the app-import check, which is the one that catches a
    feature removal that left something importing what went."""
    blueprint = _catalog()["blueprint"]
    module = _catalog()["verify"]["app"]
    path = REPO_ROOT / blueprint["python_root"] / Path(*module.split(".")).with_suffix(".py")

    assert module.split(".")[0] == blueprint["import_root"]
    assert _is_tracked_file(path), module
    assert _defines(module, "app"), "the check imports the module for its app"


def test_the_toolchain_environment_is_what_the_app_needs_to_import():
    """Spec 2.12: names and string values only. They are test values for checking a project
    rather than secrets: a memory session store, a memory limiter, the local environment, and a
    key that exists only so the settings validate.
    """
    declared = _catalog()["checks"]["toolchain"]["env"]

    assert set(declared) == {"ENVIRONMENT", "SECRET_KEY", "SESSION_BACKEND", "RATE_LIMITER_BACKEND"}
    for name, value in declared.items():
        assert ENV_VAR.match(name), name
        assert isinstance(value, str), name

    assert len(declared["SECRET_KEY"]) >= 32, "the settings refuse a shorter one"
    assert declared["SECRET_KEY"] not in ENV_EXAMPLE.read_text(), "not the example's placeholder"


def _true(condition: str, chosen: set[str]) -> bool:
    """Whether a spec 1.3 condition holds for this selection: features, and any option choices
    written as atoms (``cache.backend=memcached``). An option the selection doesn't choose has its
    default."""
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
            feature, _, rest = token.partition(".")
            option, _, value = rest.partition("=")
            named = {choice for choice in chosen if choice.startswith(f"{feature}.{option}=")}
            default = _catalog()["features"][feature]["options"][option]["default"]

            return feature in chosen and (token in named if named else value == default)

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

    for chosen in _selections():
        for point in single:
            assert len(_contributed(catalog, point, chosen)) <= 1, (point, sorted(chosen))


def test_a_transport_that_is_constructed_says_so():
    """Spec 1.5: `call` is what renders `APIKeyTransport()` rather than the class itself."""
    catalog = _catalog()
    everything = set(catalog["features"])
    entry = _contributed(catalog, "extra_transports", everything)[0]
    rendered = _defined(_committed("backend/src/wiring/transports.py"), "EXTRA_TRANSPORTS")

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
    """An option atom reads the option's default when the selection doesn't choose one."""
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


ENV_EXAMPLE = REPO_ROOT / "backend" / ".env.example"

NOT_A_SETTING = {
    "FORWARDED_ALLOW_IPS": "core",
}
"""Variables the example sets that no settings field takes: `FORWARDED_ALLOW_IPS` is read by
uvicorn and written by the deploy templates, never by the app."""


def _alias_names(node: ast.AnnAssign) -> set[str]:
    """The names a field accepts besides its own, which is how one feature's setting reads
    another's: `SESSION_REDIS_HOST` takes `CACHE_REDIS_HOST` when nothing sets it."""
    names: set[str] = set()
    for given in getattr(node.value, "keywords", ()):
        if given.arg != "validation_alias":
            continue

        if isinstance(given.value, ast.Constant) and isinstance(given.value.value, str):
            names.add(given.value.value)
        else:
            names.update(
                argument.value
                for argument in getattr(given.value, "args", ())
                if isinstance(argument, ast.Constant) and isinstance(argument.value, str)
            )

    return names


@functools.cache
def _settings_fields() -> dict[str, frozenset[str]]:
    """Which parts of the project take each setting: `core`, or the features whose contributed
    settings classes declare it, counting the names a field accepts as aliases as well."""
    modules: dict[str, list[Path]] = {"core": [REPO_ROOT / "backend/src/infrastructure/config/base.py"]}
    for name, feature in _catalog()["features"].items():
        for entry in feature.get("contributes", {}).get("settings", ()):
            module, _, _ = _ref(entry if isinstance(entry, str) else entry["ref"])
            modules.setdefault(name, []).append(REPO_ROOT / "backend" / Path(*module.split(".")).with_suffix(".py"))

    declared: dict[str, set[str]] = {}
    for owner, paths in modules.items():
        for path in paths:
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id.isupper():
                    for name in {node.target.id} | _alias_names(node):
                        declared.setdefault(name, set()).add(owner)

    return {name: frozenset(owners) for name, owners in declared.items()}


@functools.cache
def _env_comments() -> dict[str, tuple[str, ...]]:
    """Each section's comment lines, less its markers, which name variables as data."""
    lines = ENV_EXAMPLE.read_text().splitlines()
    rule = re.compile(r"^# ={10,}$")
    headers = [
        index
        for index, line in enumerate(lines)
        if rule.match(line) and index + 2 < len(lines) and rule.match(lines[index + 2])
    ]

    comments = {}
    for position, start in enumerate(headers):
        end = headers[position + 1] if position + 1 < len(headers) else len(lines)
        comments[lines[start + 1].lstrip("# ").strip()] = tuple(
            line for line in lines[start + 3 : end] if line.lstrip().startswith("#") and "@fastro" not in line
        )

    return comments


@functools.cache
def _env_sections() -> tuple[tuple[str, str | None, tuple[str, ...]], ...]:
    """Each section of the example: its title, the marker directly below its header if it carries
    one, and the variables it sets, including the ones it ships commented out, since a reader
    uncomments them where they sit."""
    lines = ENV_EXAMPLE.read_text().splitlines()
    rule = re.compile(r"^# ={10,}$")
    headers = [
        index
        for index, line in enumerate(lines)
        if rule.match(line) and index + 2 < len(lines) and rule.match(lines[index + 2])
    ]

    sections = []
    for position, start in enumerate(headers):
        end = headers[position + 1] if position + 1 < len(headers) else len(lines)
        variables = tuple(
            found.group(1) for line in lines[start + 3 : end] if (found := re.match(r"^#?\s*([A-Z][A-Z0-9_]*)=", line))
        )
        marker = lines[start + 3] if start + 3 < end and lines[start + 3].startswith("# @fastro ") else None
        sections.append((lines[start + 1].lstrip("# ").strip(), marker, variables))

    return tuple(sections)


def _owner_of(variable: str) -> frozenset[str]:
    fields = _settings_fields()
    if variable in fields:
        return fields[variable]

    assert variable in NOT_A_SETTING, f"{variable} is in the example and nothing declares it"

    return frozenset({NOT_A_SETTING[variable]})


def _owners_of(title: str) -> set[str]:
    """Every part of the project that takes any of this section's variables."""
    variables = next(found for name, _, found in _env_sections() if name == title)

    return {owner for variable in variables for owner in _owner_of(variable)}


def _common_owners_of(title: str) -> set[str]:
    """The parts that take *every* variable in the section, which is what a marker can name."""
    variables = next(found for name, _, found in _env_sections() if name == title)

    return set.intersection(*(set(_owner_of(variable)) for variable in variables)) if variables else {"core"}


def _marked_condition(title: str) -> str:
    marker = next(found for name, found, _ in _env_sections() if name == title)

    return marker.removeprefix("# @fastro if=") if marker else "core"


def _marked_feature(title: str) -> str:
    """The feature a section's marker names: the condition itself, or an option atom's feature."""
    return _marked_condition(title).split(".")[0]


@pytest.mark.parametrize("title", [title for title, _, _ in _env_sections()])
def test_every_section_of_the_example_belongs_to_one_feature_or_to_the_core(title: str):
    """Spec 6.1 keeps or drops a section whole, so a section can hold one feature's variables or
    the core's, never both: dropping a mixed one would take `SECRET_KEY` from every project
    without accounts.
    """
    assert _common_owners_of(title), sorted(_owners_of(title))


@pytest.mark.parametrize("title", [title for title, _, _ in _env_sections()])
def test_every_section_a_feature_owns_says_which_feature_keeps_it(title: str):
    """Spec 6.1: the marker is a line of its own directly below the header's closing rule, and
    the section goes when its condition is false. A core section carries none, because a project
    keeps it whatever it selected.
    """
    common = _common_owners_of(title)
    marker = next(found for name, found, _ in _env_sections() if name == title)

    if common == {"core"}:
        assert marker is None, title

        return

    assert marker is not None, sorted(common)
    assert _marked_feature(title) in common - {"core"}


@pytest.mark.parametrize("title", [title for title, _, _ in _env_sections()])
def test_no_section_sends_a_reader_to_a_variable_another_feature_owns(title: str):
    """A kept section has to read on its own: a project that selected one feature and not another
    would otherwise be told to set something it hasn't got, with nowhere to set it.

    Only variables this section's own feature declares, or the core's, may be named. The
    production checklist is the reason this exists: it used to name eight of them.
    """
    mine = {_marked_feature(title)}
    named = {
        word
        for line in _env_comments()[title]
        for word in re.findall(r"\b[A-Z][A-Z0-9_]{2,}\b", line)
        if word in _settings_fields() or word in NOT_A_SETTING
    }

    assert {word: sorted(_owner_of(word)) for word in named if not _owner_of(word) & (mine | {"core"})} == {}


@functools.cache
def _fields_falling_back_to_another_feature() -> dict[str, frozenset[str]]:
    """Fields that read another feature's variable when nothing sets their own, with the features
    whose names they borrow. `SESSION_REDIS_HOST` takes `CACHE_REDIS_HOST`, so a project with
    accounts and no cache has nothing in its example pointing sessions at Redis."""
    fields: dict[str, set[str]] = {}
    for name, feature in _catalog()["features"].items():
        for entry in feature.get("contributes", {}).get("settings", ()):
            module, _, _ = _ref(entry if isinstance(entry, str) else entry["ref"])
            path = REPO_ROOT / "backend" / Path(*module.split(".")).with_suffix(".py")
            for node in ast.walk(ast.parse(path.read_text())):
                if not isinstance(node, ast.AnnAssign) or not isinstance(node.target, ast.Name):
                    continue

                borrowed = {
                    owner for alias in _alias_names(node) - {node.target.id} for owner in _owner_of(alias) if owner != name
                }
                if borrowed:
                    fields.setdefault(node.target.id, set()).update(borrowed)

    return {name: frozenset(owners) for name, owners in fields.items()}


@pytest.mark.parametrize("field", sorted(_fields_falling_back_to_another_feature()))
def test_every_setting_that_borrows_another_features_variable_is_named_in_its_own_section(field: str):
    """Otherwise the only line that sets it is the other feature's, and a project without that
    feature is left with the default: for the session Redis, `localhost`, which is not the
    service name the compose stack publishes.

    The line may be commented out. It is there to be found and uncommented, and a live one would
    beat the borrowed value rather than fall back to it.
    """
    owners = _owner_of(field) - _fields_falling_back_to_another_feature()[field]
    sections = {title: variables for title, _, variables in _env_sections()}
    theirs = [title for title in sections if _marked_feature(title) in owners]

    assert theirs, sorted(owners)
    assert any(field in sections[title] for title in theirs), (
        f"{field} is set only by {sorted(_fields_falling_back_to_another_feature()[field])}"
    )


def test_the_comments_are_read_the_way_they_are_written():
    """The reading above: comments that stopped being found would leave it nothing to object to."""
    comments = _env_comments()

    assert any("SECRET_KEY" in line for line in comments["Production Security Checklist"])
    assert any("CACHE_REDIS_DB" in line for line in comments["Cache Configuration"])
    assert not any("@fastro" in line for section in comments.values() for line in section)


def test_no_marker_sits_anywhere_but_under_a_header():
    """A marker further down would speak for the lines after it, which spec 6.1 doesn't read:
    the section is what the condition keeps or drops."""
    lines = ENV_EXAMPLE.read_text().splitlines()
    marked = [line for line in lines if line.startswith("# @fastro if=")]
    under_headers = [marker for _, marker, _ in _env_sections() if marker is not None]

    assert marked == under_headers
    for marker in marked:
        condition = marker.removeprefix("# @fastro if=")
        choosing = set(re.findall(r"[^\s()]+=[^\s()]+", condition))
        for atom in choosing:
            feature, _, rest = atom.partition(".")
            option, _, value = rest.partition("=")
            assert value in _catalog()["features"][feature]["options"][option]["choices"], atom
        assert _true(condition, set(_catalog()["features"]) | choosing), condition


CHOSEN_SERVICES = {"cache.backend=memcached": "CACHE_MEMCACHED_", "taskiq.broker=rabbitmq": "TASKIQ_RABBITMQ_"}


@pytest.mark.parametrize(("choice", "prefix"), CHOSEN_SERVICES.items())
def test_a_chosen_service_s_settings_are_kept_only_where_it_is_chosen(choice: str, prefix: str):
    """A project without the choice runs no such service to point anywhere, so its example names
    none, neither as a setting nor in the comments of a section it keeps."""
    settings = {name for name in _settings_fields() if name.startswith(prefix)}
    holding = [(title, marker, set(variables)) for title, marker, variables in _env_sections() if settings & set(variables)]
    naming = {
        title
        for title, comments in _env_comments().items()
        if any(word.startswith(prefix) for line in comments for word in re.findall(r"\b[A-Z][A-Z0-9_]{2,}", line))
    }

    assert settings
    assert [(marker, variables) for _, marker, variables in holding] == [(f"# @fastro if={choice}", settings)]
    assert naming <= {title for title, _, _ in holding}


@pytest.mark.parametrize(("choice", "prefix"), CHOSEN_SERVICES.items())
def test_every_page_that_sets_a_chosen_service_names_the_choice_that_brings_it(choice: str, prefix: str):
    """A page choosing the service, or setting its own settings, is speaking to a project generated
    with that choice, and has to say so, or a reader without it follows it to a service that isn't there."""
    feature, _, rest = choice.partition(".")
    option, _, value = rest.partition("=")
    (variable,) = _catalog()["features"][feature]["options"][option]["env"]
    setting = rf"^\s*(?:{re.escape(prefix)}\w+=|{re.escape(variable)}={re.escape(value)}\b)"
    pages = [page for page in _tracked(REPO_ROOT / "docs", "*.md") if page.name != "changelog.md"]
    setting_it = [page.relative_to(REPO_ROOT).as_posix() for page in pages if re.search(setting, page.read_text(), re.M)]

    assert setting_it
    assert [page for page in setting_it if f"`{choice}`" not in (REPO_ROOT / page).read_text()] == []


def test_no_page_offers_the_other_cache_backend_as_a_setting():
    """Every project has Redis, and only one generated with `cache.backend=memcached` has
    Memcached, so a page that offers a backend as the alternative value of `CACHE_BACKEND` sends a
    reader on Redis to a backend that isn't there."""
    offered = [
        f"{page.relative_to(REPO_ROOT)}: {line.strip()}"
        for page in _tracked(REPO_ROOT / "docs", "*.md")
        if page.name != "changelog.md"
        for line in page.read_text().splitlines()
        if re.match(r"^\s*CACHE_BACKEND=\w+.*#.*\b(?:redis|memcached)\b", line)
    ]

    assert offered == []


RATE_LIMITER_PAGE = REPO_ROOT / "docs" / "user-guide" / "rate-limiting" / "index.md"

NAMES_THE_LIMITER = re.compile(r"\brate[- ]limit|\blimiter\b", re.I)

PRODUCTION_PAGE = REPO_ROOT / "docs" / "user-guide" / "production.md"

REDIS_ALONE = re.compile(
    r"redis[- ](?:backed|based|only)|backed by redis|always redis|only redis|redis alone"
    r"|\bredis (?:rate[- ]limit|limiter)|\b(?:limit\w*|limiter|count\w*) (?:in|on) redis\b",
    re.I,
)
"""The ways a line says Redis is the store, where the limiter's is whichever ``RATE_LIMITER_BACKEND`` names."""


def _limiter_backends() -> set[str]:
    """The values ``RATE_LIMITER_BACKEND`` takes."""
    return {backend.value for backend in importlib.import_module("src.infrastructure.config.enums").RateLimiterBackend}


def _doc_lines() -> list[tuple[str, str]]:
    """Each line of every page but the changelog, with where it is."""
    return [
        (f"{page.relative_to(REPO_ROOT)}:{number}", line)
        for page in _tracked(REPO_ROOT / "docs", "*.md")
        if page.name != "changelog.md"
        for number, line in enumerate(page.read_text().splitlines(), 1)
    ]


def _backends_named(text: str) -> set[str]:
    """The limiter backends, Memcached among them, that ``text`` names outside the words saying Memcached's went."""
    kept = re.sub(r"memcached (?:backend|limiter)s? (?:was|were)(?: both)? removed", "", text, flags=re.I)
    return {word for word in re.findall(r"[a-z]+", kept.lower()) if word in _limiter_backends() | {"memcached"}}


def test_every_limiter_backend_a_page_sets_is_one_the_code_has():
    setting = [(where, value) for where, line in _doc_lines() for value in re.findall(r"RATE_LIMITER_BACKEND=(\w+)", line)]

    assert setting
    assert [(where, value) for where, value in setting if value not in _limiter_backends()] == []


def test_a_page_that_offers_the_limiter_backends_offers_each_one_the_code_has():
    """A list that leaves one out hides it from the reader choosing, and one with Memcached in it sends
    them to a refusal at startup. The rate limiting page lists them in the first sentence above the
    setting."""
    offering = [
        (where, line)
        for where, line in _doc_lines()
        if (commented := re.search(r"RATE_LIMITER_BACKEND=(\w+)\s+#(.*)", line))
        and len(_backends_named(commented[2]) | {commented[1]}) > 1
    ]
    explained = re.search(r"((?:^#.*\n)+)RATE_LIMITER_BACKEND=", RATE_LIMITER_PAGE.read_text(), re.M)

    assert offering
    assert explained is not None
    listing = re.split(r"(?<=\.)\s", " ".join(line.lstrip("# ") for line in explained[1].splitlines()))[0]
    assert _backends_named(listing) == _limiter_backends()
    assert [(where, line) for where, line in offering if _backends_named(line) != _limiter_backends()] == []


def test_no_page_gives_the_limiter_a_backend_it_does_not_have():
    """The counters live where ``RATE_LIMITER_BACKEND`` says, so the limiter is not Redis's alone, and
    never in Memcached, whose limiter was removed."""
    claiming = [
        f"{where}: {line.strip()}"
        for where, line in _doc_lines()
        if NAMES_THE_LIMITER.search(line) and ("memcached" in _backends_named(line) or REDIS_ALONE.search(line))
    ]

    assert claiming == []


def test_the_production_example_counts_where_the_production_check_lets_it():
    """The example is what a reader copies into production, where the validator refuses a limiter
    counting in the process; the backends its comment calls refused are the ones the validator refuses."""
    validator = importlib.import_module("src.infrastructure.security.production_validator").ProductionSecurityValidator
    line = re.search(r"^RATE_LIMITER_BACKEND=(\w+)\s+#(.*)$", PRODUCTION_PAGE.read_text(), re.M)

    def refused(backend: str) -> bool:
        return bool(validator(type("Settings", (), {"RATE_LIMITER_BACKEND": backend})())._counts_rate_limits_in_the_process())

    assert line is not None
    said_refused = _backends_named(next(clause for clause in line[2].split(";") if "refused" in clause))
    assert not refused(line[1])
    assert said_refused == {backend for backend in _limiter_backends() if refused(backend)}


ADMIN_GUIDE = REPO_ROOT / "docs" / "user-guide" / "admin-panel" / "configuration.md"

QUOTED_EXAMPLE = "The default `.env.example`"
"""Where that guide quotes the example, which is the one place the docs reproduce its values."""


def test_the_guide_quotes_the_example_as_it_ships():
    """A quoted value that drifts from the file is a reader setting up a panel that stays dark, or
    serving one they thought was off: the example keeps the admin panel off, as the setting's own
    default has since 0.20.0."""
    guide = ADMIN_GUIDE.read_text()
    quoted = guide[guide.index(QUOTED_EXAMPLE) :].split("```")[1].removeprefix("env\n")
    shipped = dict(line.split("=", 1) for line in ENV_EXAMPLE.read_text().splitlines() if re.match(r"^[A-Z][A-Z0-9_]*=", line))

    assert "ADMIN_ENABLED=false" in quoted, "the example ships the panel off"
    for line in quoted.splitlines():
        name, _, value = line.partition("=")
        assert shipped[name] == value, name


FIRST_RUN = REPO_ROOT / "docs" / "getting-started"

NEARBY_LINES = 2
"""How far from a mention of the panel the flag may be and still be read as part of the same claim."""


@pytest.mark.parametrize("page", [path.name for path in _tracked(FIRST_RUN, "*.md", recursive=False)])
def test_no_first_run_page_offers_the_admin_panel_without_saying_what_turns_it_on(page: str):
    """A new reader follows these pages in order, and `/admin` answers 404 until the flag is set
    and both credentials are there. A page that lists it among the things that now work sends
    that reader to look for a bug of their own."""
    lines = (FIRST_RUN / page).read_text().splitlines()
    unexplained = [
        line
        for index, line in enumerate(lines)
        if "/admin" in line and "ADMIN_ENABLED" not in "\n".join(lines[max(0, index - NEARBY_LINES) : index + NEARBY_LINES + 1])
    ]

    assert unexplained == []


def test_the_example_is_read_the_way_it_is_written():
    """The reading itself: a parse that found no sections, or missed the commented-out lines,
    would leave the rule above with nothing to object to."""
    sections = {title: variables for title, _, variables in _env_sections()}

    assert len(sections) >= 15
    assert "CREATE_TABLES_ON_STARTUP" in sections["Database Configuration"], "a line shipped commented out"
    assert _owner_of("SECRET_KEY") == frozenset({"core"})
    assert _owner_of("CACHE_BACKEND") == frozenset({"cache"})
    assert _owner_of("SESSION_REDIS_URL") == frozenset({"accounts"})
    assert _owner_of("CACHE_REDIS_HOST") == frozenset({"accounts", "cache"}), "the session host takes it too"


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


@pytest.mark.parametrize("path", [entry["path"] for entry in _entries()])
def test_every_wiring_file_is_under_the_python_root_and_is_a_file(path: str):
    """Spec 2.6: a generated Python file lives under `python_root`, and names one file."""
    blueprint = _catalog()["blueprint"]

    assert path.startswith(blueprint["python_root"] + "/")
    assert not path.endswith("/")
    assert _is_tracked_file(REPO_ROOT / path)


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

    assert admin["if"] == "admin"
    assert [entry.get("if") for entry in _entries()].count(None) == 13


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


def test_the_hand_written_module_says_who_writes_the_ones_beside_it():
    """It is not generated, so it is where the reason lives: once, in the file a person edits."""
    docstring = _docstring(_committed(HAND_WRITTEN))

    assert HAND_WRITTEN not in [entry["path"] for entry in _entries()]
    assert docstring is not None
    assert "fastro" in docstring
    assert "blueprint.toml" in docstring
    assert "imports and literals" in docstring


LINE_LENGTH = _catalog()["wiring_defaults"]["line_length"]
"""Spec 2.12: the length spec 2.8 wraps a generated import at, declared rather than assumed."""


def test_the_generated_line_length_is_the_one_ruff_holds_the_project_to():
    """Spec 2.12: an integer from 1 to 320. Declared shorter than ruff's, fastro would wrap an
    import ruff is happy with; longer, and `ruff format --check` fails on a file nobody edited.
    """
    with BACKEND_PYPROJECT.open("rb") as handle:
        backend = tomllib.load(handle)

    assert 1 <= LINE_LENGTH <= 320
    assert LINE_LENGTH == backend["tool"]["ruff"]["line-length"]


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

ENV_VAR = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
"""Spec 2.5 and 2.12: the name of an environment variable."""

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

    assert _is_tracked_dir(templates)
    assert any(path.parent != templates for path in _tracked(templates, "*"))


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
    network = ipaddress.ip_network(declared["default"], strict=True)

    assert str(network) == declared["default"]
    assert network.prefixlen >= declared["max_prefix"][f"v{network.version}"], "the default meets its own limit"


def test_the_subnet_limit_is_set_for_both_families():
    """Spec 2.9: a table with both `v4` (0 to 32) and `v6` (0 to 128), because one integer can't
    carry the two. An IPv6 limit of 8 would accept a `/16`, which is half the address space.
    """
    limits = _catalog()["generators"]["deploy"]["params"]["internal_subnet"]["max_prefix"]

    assert set(limits) == {"v4", "v6"}
    assert 0 <= limits["v4"] <= 32
    assert 0 <= limits["v6"] <= 128


def test_every_param_the_templates_read_is_a_param_the_catalog_declares():
    """Both ways: an undeclared param is a StrictUndefined crash, a declared one nothing reads is dead."""
    generator = _catalog()["generators"]["deploy"]
    templates = REPO_ROOT / generator["templates"]
    read = {name for template in _tracked(templates, "*.j2") for name in re.findall(r"params\.([a-z_]+)", template.read_text())}

    assert read == set(generator["params"])


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

    assert _is_tracked_file(path), words
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
        for script in _tracked(directory, recursive=False)
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
    features = _catalog()["features"]
    owned = _owned_paths()

    for chosen in _selections():
        kept = _kept_by_the_catalog(features, chosen)
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


RETIRED_NAME = "fastro".title()

STILL_CARRYING_THE_RETIRED_NAME = {
    "docs/changelog.md": "B9 item 15",
    "docs/assets/build-cover.cjs": "B5",
    "docs/assets/build-card.cjs": "B5",
}
"""Files left as they are until the item named beside each, which rewrites them."""


def test_no_tracked_file_calls_the_blueprint_by_its_retired_name():
    """FastAPI-boilerplate is the blueprint, fastro the tool and FastroAI the paid blueprint: the
    capitalised tool name, standing alone, names nothing. A wordmark that sets AI in its own
    `<tspan>` straight after it still spells FastroAI."""
    alone = re.compile(rf"\b{RETIRED_NAME}\b(?!<tspan[^>]*>AI</tspan>)")
    found = []
    carrying = set()
    for path in _tracked_files():
        name = path.relative_to(REPO_ROOT).as_posix()
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        hits = [f"{name}:{number}" for number, line in enumerate(text.splitlines(), 1) if alone.search(line)]
        if name in STILL_CARRYING_THE_RETIRED_NAME:
            carrying |= {name} if hits else set()
        else:
            found += hits

    assert not found, found
    assert carrying == set(STILL_CARRYING_THE_RETIRED_NAME), "drop the exemption of a file that no longer carries it"
