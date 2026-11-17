"""Every module of the composition root is drawn where the guides draw it.

The two pages that enumerate `src/wiring/` drew five of its ten modules for as long as the
other five existed: a reader following either one would not know that the sender, the task
modules, the tables, the transports and the cache decorator are wired there too. The diagram
beside them is generated from a script, which is text, so it is held to the same list.
"""

import re
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
WIRING = REPO_ROOT / "backend" / "src" / "wiring"
STRUCTURE = REPO_ROOT / "docs" / "user-guide" / "project-structure.md"
COMPOSABLE = REPO_ROOT / "docs" / "user-guide" / "composable-features.md"
DIAGRAMS = REPO_ROOT / "docs" / "assets" / "build-diagrams.cjs"

DRAWN_TREE = re.compile(r"```text\n(.*?)```", re.DOTALL)


def _wiring_modules() -> list[str]:
    return sorted(path.name for path in WIRING.glob("*.py") if path.name != "__init__.py")


def _tree_drawing_the_wiring() -> str:
    """The structure guide's fenced tree for ``src/wiring/``."""
    trees = [tree for tree in DRAWN_TREE.findall(STRUCTURE.read_text()) if tree.startswith("wiring/")]
    assert len(trees) == 1, f"expected one wiring tree in the structure guide, found {len(trees)}"

    return str(trees[0])


def test_the_structure_guide_draws_every_module_of_the_composition_root():
    tree = _tree_drawing_the_wiring()

    assert [name for name in _wiring_modules() if name not in tree] == []


def test_the_composable_features_page_lists_every_module_of_the_composition_root():
    page = COMPOSABLE.read_text()

    assert [name for name in _wiring_modules() if f"`{name}`" not in page] == []


def test_the_sweep_reads_what_it_claims_to():
    """A glob that stopped matching, or a tree nothing finds, would make it vacuous."""
    modules = _wiring_modules()

    assert "app.py" in modules
    assert "__init__.py" not in modules
    assert "app.py" in _tree_drawing_the_wiring()


def test_the_diagram_draws_every_module_of_the_composition_root():
    """The picture is generated from this script, so the script is what holds the list."""
    drawn = DIAGRAMS.read_text()

    assert [name for name in _wiring_modules() if name not in drawn] == []


def test_the_diagram_names_every_set_verify_sets_declares():
    """A set added to `[verify.sets]` and not to the picture is a diagram that has aged."""
    with (REPO_ROOT / "blueprint.toml").open("rb") as handle:
        sets = tomllib.load(handle)["verify"]["sets"]
    drawn = set(re.findall(r">([a-z0-9-]+)</text>", DIAGRAMS.read_text()))

    assert sets
    assert [name for name in sets if name not in drawn] == []
