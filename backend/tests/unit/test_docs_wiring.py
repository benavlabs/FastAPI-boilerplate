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
CHANGELOG = REPO_ROOT / "docs" / "changelog.md"

DRAWN_TREE = re.compile(r"```text\n(.*?)```", re.DOTALL)


def _catalog() -> dict:
    with (REPO_ROOT / "blueprint.toml").open("rb") as handle:
        return tomllib.load(handle)


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
    sets = _catalog()["verify"]["sets"]
    drawn = set(re.findall(r">([a-z0-9-]+)</text>", DIAGRAMS.read_text()))

    assert sets
    assert [name for name in sets if name not in drawn] == []


def _section(page: Path, heading: str) -> str:
    text = page.read_text()
    assert heading in text, heading

    return text.split(heading, 1)[1].split("\n## ", 1)[0]


def test_the_ci_table_is_every_declared_set_and_names_the_presets_beside_it():
    """CI runs `fastro blueprint verify` once for each set: the declared ones, each preset and `everything`."""
    section = _section(COMPOSABLE, "## Checking that removal still works")
    rows = re.findall(r"^\| `([a-z0-9-]+)` \|", section, re.M)
    catalog = _catalog()

    assert rows == [*catalog["verify"]["sets"], "everything"]
    assert [preset for preset in catalog["presets"] if f"`{preset}`" not in section] == []


def test_the_steps_for_a_removable_feature_declare_it_in_the_catalog_and_verify_it():
    section = _section(COMPOSABLE, "## Writing a feature that can be removed")

    assert "`blueprint.toml`" in section and "`[features.<name>]`" in section
    assert "`[[features.<name>.when]]`" in section and 'if = "<other>"' in section
    assert "`fastro blueprint verify`" in section
    assert any(feature.get("when") for feature in _catalog()["features"].values())


def test_the_new_module_steps_declare_its_paths_in_the_catalog():
    steps = STRUCTURE.read_text().split("**Generate a migration**", 1)[0]

    assert "`blueprint.toml`" in steps.rsplit("\n9. ", 1)[1]
    assert "`fastro blueprint verify`" in steps.rsplit("\n9. ", 1)[1]


def test_the_changelog_names_the_wiring_the_cache_reads_the_scope_fingerprint_from():
    unreleased = CHANGELOG.read_text().split("## Unreleased", 1)[1].split("\n## ", 1)[0]
    entry = unreleased.split("**A project with the cache feature and without accounts imports.**", 1)[1].split("\n- **", 1)[0]
    wiring = next(module for module in _catalog()["wiring"] if module["path"] == "backend/src/wiring/scope.py")
    (slot,) = wiring["slots"]

    assert f"`{slot['name']}`" in entry and f"{slot['name']}:" in (WIRING / "scope.py").read_text()
    assert "`src/wiring/scope.py`" in entry
    assert slot["fallback"] == "None" and "`None` without accounts" in entry


def test_the_changelog_names_the_test_a_project_without_the_cache_no_longer_ships():
    unreleased = CHANGELOG.read_text().split("## Unreleased", 1)[1].split("\n## ", 1)[0]
    entry = unreleased.split("**A project with the cache feature and without accounts imports.**", 1)[1].split("\n- **", 1)[0]
    path = "tests/integration/tier_limits/test_cached_listing.py"
    (block,) = [block for block in _catalog()["features"]["tier_limits"]["when"] if f"backend/{path}" in block["paths"]]

    assert f"`{path}`" in " ".join(entry.split())
    assert block["if"] == "cache"


def test_the_composable_features_page_says_the_scope_fingerprint_is_none_without_accounts():
    (row,) = [line for line in COMPOSABLE.read_text().splitlines() if line.startswith("| `scope.py` |")]
    wiring = next(module for module in _catalog()["wiring"] if module["path"] == "backend/src/wiring/scope.py")
    (slot,) = wiring["slots"]

    assert slot["fallback"] == "None" and "`None` without it" in row
