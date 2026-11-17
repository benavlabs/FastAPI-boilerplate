"""The observability guide's tracing recipe, followed in a copy of the repository."""

import ast
import re
import tomllib
from pathlib import Path

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
