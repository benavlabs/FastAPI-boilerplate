"""Every module of the composition root is drawn where the guides draw it.

The two pages that enumerate `src/wiring/` drew five of its ten modules for as long as the
other five existed: a reader following either one would not know that the sender, the task
modules, the tables, the transports and the cache decorator are wired there too.
"""

import re
from pathlib import Path

from tests.unit.test_docs_imports import LEFT_OUT_PATHS

REPO_ROOT = Path(__file__).resolve().parents[3]
WIRING = REPO_ROOT / "backend" / "src" / "wiring"
STRUCTURE = REPO_ROOT / "docs" / "user-guide" / "project-structure.md"
COMPOSABLE = REPO_ROOT / "docs" / "user-guide" / "composable-features.md"

DRAWN_TREE = re.compile(r"```text\n(.*?)```", re.DOTALL)


def _wiring_modules() -> list[str]:
    """The composition root's modules, as a project that carries them has them."""
    return sorted(
        path.name
        for path in WIRING.glob("*.py")
        if path.name != "__init__.py" and f"backend/src/wiring/{path.name}" not in LEFT_OUT_PATHS
    )


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
