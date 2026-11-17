"""The observability guide's tracing recipe, followed in a copy of the repository."""

import ast
import re
import tomllib
from pathlib import Path

import pytest
from conftest import Fastro

REPO_ROOT = Path(__file__).resolve().parents[2]
RECIPE = REPO_ROOT / "docs" / "user-guide" / "observability.md"


def _blocks(language: str) -> list[str]:
    return [str(block) for block in re.findall(rf"^```{language}\n(.*?)^```$", RECIPE.read_text(), re.M | re.S)]


def _block(language: str) -> str:
    blocks = _blocks(language)
    assert len(blocks) == 1, f"expected one {language} block in the recipe, found {len(blocks)}"

    return blocks[0]


def _python_block_defining(name: str) -> str:
    for block in _blocks("python"):
        if any(isinstance(node, ast.FunctionDef) and node.name == name for node in ast.parse(block).body):
            return block
    raise AssertionError(f"no python block in the recipe defines {name}()")


def _installers_slot() -> tuple[str, str]:
    """The wiring file whose slot holds the installers point, and that slot's name."""
    catalog = tomllib.loads((REPO_ROOT / "blueprint.toml").read_text())
    return next(
        (wiring["path"], slot["name"])
        for wiring in catalog["wiring"]
        for slot in wiring.get("slots", [])
        if slot.get("point") == "installers"
    )


def test_the_recipe_registers_its_installer_through_fastro_toml_and_a_sync(tracked_tree: Path, fastro: Fastro):
    project = tracked_tree
    wiring_file, slot = _installers_slot()
    registration = _block("toml")
    reference = re.search(r'installers = \["([\w.]+):(\w+) as (\w+)"\]', registration)
    assert reference, registration
    module, function, alias = reference.groups()
    (project / "backend" / f"{module.replace('.', '/')}.py").write_text(_python_block_defining(function))
    with (project / "fastro.toml").open("a") as handle:
        handle.write(f"\n{registration}")
    wiring_path = project / wiring_file

    synced = fastro("sync", cwd=project)
    wiring = wiring_path.read_text()

    assert synced.returncode == 0, synced.stdout + synced.stderr
    assert f"from ..{module.removeprefix('src.')} import {function} as {alias}" in wiring
    installers = re.search(rf"^{slot}\b.*?= \(\n(.*?)^\)", wiring, re.M | re.S)
    assert installers, wiring
    assert installers[1].splitlines()[-1].strip() == f"{alias},", installers[1]
    recipe = RECIPE.read_text()
    assert {f"`{alias}`", f"`{slot}`", f"`{wiring_file.removeprefix('backend/')}`", "`fastro sync --check`"} <= set(
        re.findall(r"`[^`\n]+`", recipe)
    )
    assert re.search(rf"^\| [^|]*\| `{re.escape(wiring_file)}` \|$", recipe, re.M)
    assert re.search(r"^\| [^|]*\| `fastro.toml`, under `\[app.contributes\]` \|$", recipe, re.M)
    assert fastro("sync", "--check", cwd=project).returncode == 0
    assert any("fastro sync" in block.splitlines() for block in _blocks("bash"))

    wiring_path.write_text(wiring.replace(f"    {alias},\n", ""))
    assert fastro("sync", "--check", cwd=project).returncode == 1
    assert fastro("sync", cwd=project).returncode == 0
    assert wiring_path.read_text() == wiring


def test_the_registered_module_is_the_one_the_recipe_writes():
    registration = _block("toml")
    module = re.search(r'installers = \["([\w.]+):', registration)
    assert module, registration
    path = f"backend/{module[1].replace('.', '/')}.py"

    assert f"`{path.removeprefix('backend/')}`" in RECIPE.read_text()
    assert re.search(rf'^paths = \["{re.escape(path)}"\]$', registration, re.M), registration


def test_the_installer_configures_tracing_before_it_instruments_the_app():
    """Registered as an installer, `install` is all the app calls, so it has to configure Logfire itself."""
    module = ast.parse(_python_block_defining("install"))
    install = next(node for node in module.body if isinstance(node, ast.FunctionDef) and node.name == "install")
    calls = [ast.unparse(node.func) for node in ast.walk(install) if isinstance(node, ast.Call)]

    assert any(isinstance(node, ast.FunctionDef) and node.name == "configure_tracing" for node in module.body)
    assert calls.index("configure_tracing") < calls.index("logfire.instrument_fastapi"), calls


@pytest.mark.parametrize("arguments", [("sync",), ("sync", "--check")])
def test_the_pinned_fastro_cannot_sync_a_project_yet(tracked_tree: Path, fastro: Fastro, arguments: tuple[str, ...]):
    """The recipe's hand-edit fallback is there only while this holds; when it fails, delete that sentence."""
    config = tracked_tree / "fastro.toml"
    config.write_text(re.sub(r"^source = true\n", "", config.read_text(), flags=re.M))

    synced = fastro(*arguments, cwd=tracked_tree)

    assert f"`fastro {' '.join(arguments)}`" in RECIPE.read_text()
    assert synced.returncode != 0
    assert "fastro sync in a project isn't here yet" in synced.stdout + synced.stderr, (
        "the pinned fastro syncs projects now: drop the main.py fallback sentence from observability.md"
    )


def test_the_hand_edit_fallback_names_the_lines_main_py_has_and_the_recipe_registers(tracked_tree: Path):
    recipe = RECIPE.read_text()
    reference = re.search(r'installers = \["([\w.]+):(\w+) as (\w+)"\]', _block("toml"))
    assert reference, recipe
    module, function, alias = reference.groups()
    importing = f"from ..{module.removeprefix('src.')} import {function} as {alias}"
    passed, replaced = re.findall(r"`(installers=[^`]+,)`", recipe)
    main = tracked_tree / "backend" / "src" / "interfaces" / "main.py"
    source = main.read_text()

    assert f"`{importing}`" in recipe
    assert f"`{main.relative_to(tracked_tree / 'backend')}`" in recipe
    assert "`fastro sync`" in recipe and "project-mode sync" in recipe
    assert source.count(f"    {passed}\n") == 1, passed
    assert replaced == f"installers=(*INSTALLERS, {alias}),", replaced
    edited = f"{importing}\n{source.replace(f'    {passed}', f'    {replaced}')}"
    ast.parse(edited)


def test_the_worker_note_names_the_worker_module_and_a_call_configure_tracing_takes():
    recipe = RECIPE.read_text()
    command = re.search(r"`taskiq worker (src(?:\.\w+)+):(\w+)`", recipe)
    assert command, recipe
    worker = REPO_ROOT / "backend" / f"{command[1].replace('.', '/')}.py"
    tree = ast.parse(worker.read_text())
    bound = {
        target.id
        for node in tree.body
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name)
    }
    bound |= {alias.asname or alias.name for node in tree.body if isinstance(node, ast.ImportFrom) for alias in node.names}
    imported = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    imported |= {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
    call = re.search(r"`(configure_tracing\([^`]*\))`", recipe)
    assert call, recipe
    configure = next(
        node
        for node in ast.parse(_python_block_defining("configure_tracing")).body
        if isinstance(node, ast.FunctionDef) and node.name == "configure_tracing"
    )
    given = ast.parse(call[1], mode="eval").body
    assert isinstance(given, ast.Call)

    assert command[2] in bound
    assert f"`{worker.relative_to(REPO_ROOT / 'backend')}`" in recipe
    assert not any(module and module.endswith("interfaces.main") for module in imported)
    assert {keyword.arg for keyword in given.keywords} <= {argument.arg for argument in configure.args.args}
    assert given.keywords
    defaults = dict(
        zip([argument.arg for argument in configure.args.args][-len(configure.args.defaults) :], configure.args.defaults)
    )
    for keyword in given.keywords:
        assert ast.literal_eval(keyword.value) != ast.literal_eval(defaults[keyword.arg]), keyword.arg


def test_the_feature_section_names_the_tables_a_feature_is_declared_with():
    """A project's own code is `[app]`; a feature lives in the blueprint's catalog, with these tables."""
    section = RECIPE.read_text().split("## If you turn this into a feature", 1)[1].split("\n## ", 1)[0]
    catalog = tomllib.loads((REPO_ROOT / "blueprint.toml").read_text())
    feature = re.search(r"`\[features\.(\w+)\]`", section)
    assert feature, section
    name = feature[1]

    assert "tools/removal_drill.py" not in section
    assert "`blueprint.toml`" in section and "`[app]`" in section
    assert "`paths`" in section and f"`[features.{name}.contributes]`" in section
    assert any(
        "paths" in declared and "installers" in declared.get("contributes", {}) for declared in catalog["features"].values()
    )
