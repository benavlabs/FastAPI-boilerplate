"""Every script a reader can run is drawn in each tree the structure guide draws it in.

A script is found by those trees, so one missing from either is one nobody runs: the usage
prune was absent from both. A module the scripts import rather than run, and the one the
generator writes, are not drawn there and are not asked for.
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = REPO_ROOT / "backend" / "scripts"
STRUCTURE = REPO_ROOT / "docs" / "user-guide" / "project-structure.md"

DRAWN_TREE = re.compile(r"```text\n(.*?)```", re.DOTALL)

RUNNABLE = "__main__"
"""What a script a reader runs has, which the modules beside them do not."""


MIGRATIONS = REPO_ROOT / "docs" / "user-guide" / "database" / "migrations.md"
"""The one guide whose manual recipe is a script of its own done by hand."""


def test_the_migrations_guide_names_the_script_that_writes_the_baseline():
    """`scripts/baseline.py` does what that recipe does, and a reader has no way to know it."""
    assert "python -m scripts.baseline" in MIGRATIONS.read_text()


def _runnable_scripts() -> list[str]:
    return sorted(path.name for path in SCRIPTS.glob("*.py") if RUNNABLE in path.read_text())


def _trees_drawing_the_scripts() -> list[str]:
    """Every fenced tree that draws the scripts directory: the backend's and the scripts' own."""
    return [tree for tree in DRAWN_TREE.findall(STRUCTURE.read_text()) if "scripts/" in tree]


def test_every_tree_drawing_the_scripts_draws_every_one_a_reader_can_run():
    missing = {
        tree.splitlines()[0]: [name for name in _runnable_scripts() if name not in tree]
        for tree in _trees_drawing_the_scripts()
    }

    assert missing == {"backend/": [], "scripts/": []}


def test_the_sweep_reads_what_it_claims_to():
    """A glob that stopped matching, or a tree nothing finds, would make it vacuous."""
    runnable = _runnable_scripts()

    assert len(_trees_drawing_the_scripts()) == 2
    assert "create_tables.py" in runnable
    assert "seeders.py" not in runnable
