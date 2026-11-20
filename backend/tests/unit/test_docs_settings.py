"""Every settings class the documentation names is one the code has.

A page that sends a reader to a class that isn't there leaves them grepping for it. A
class a page defines in its own sample, to show how a project's settings would look, is
the page's own; pydantic's ``BaseSettings`` is pydantic's; the changelog names classes as
they were when each release shipped.
"""

import ast
import importlib
import inspect
import re
from pathlib import Path

from pydantic_settings import BaseSettings

REPO_ROOT = Path(__file__).resolve().parents[3]
SRC_ROOT = REPO_ROOT / "backend" / "src"
PAGES = sorted([*(REPO_ROOT / "docs").rglob("*.md"), REPO_ROOT / "README.md"])
HISTORY = REPO_ROOT / "docs" / "changelog.md"

SETTINGS_NAME = re.compile(r"\b[A-Z][A-Za-z]*Settings\b")
BACKTICKED_SETTINGS = re.compile(r"`([A-Z][A-Za-z]*Settings)`")
SOURCE_PATH = re.compile(r"`(?:backend/)?(src/[\w/]+\.py)`")
TABLE_ROW = re.compile(r"^\| `([A-Z][A-Za-z]*Settings)` \| (.+) \|$")
BACKTICKED_FIELD = re.compile(r"`([A-Z][A-Z0-9_*]+)`")
DEFINED_IN_A_SAMPLE = re.compile(r"^\s*class ([A-Z][A-Za-z]*Settings)\b", re.MULTILINE)


def _classes_in_the_code() -> set[str]:
    return {
        node.name
        for path in SRC_ROOT.rglob("*.py")
        for node in ast.walk(ast.parse(path.read_text()))
        if isinstance(node, ast.ClassDef)
    }


def test_every_settings_class_a_page_names_exists():
    known = _classes_in_the_code() | {"BaseSettings"}
    missing = []
    for page in PAGES:
        if page == HISTORY:
            continue
        text = page.read_text()
        own = set(DEFINED_IN_A_SAMPLE.findall(text))
        for number, line in enumerate(text.splitlines(), 1):
            missing += [
                f"{page.relative_to(REPO_ROOT)}:{number}: {name}"
                for name in SETTINGS_NAME.findall(line)
                if name not in known and name not in own
            ]

    assert not missing, "\n".join(missing)


def _defined_in(path: Path) -> set[str]:
    return {node.name for node in ast.walk(ast.parse(path.read_text())) if isinstance(node, ast.ClassDef)}


def test_a_settings_class_named_beside_a_module_is_defined_in_it():
    """A line that sends the reader to a file for a class sends them to the file that defines it."""
    wrong = []
    for page in PAGES:
        if page == HISTORY:
            continue
        for number, line in enumerate(page.read_text().splitlines(), 1):
            modules = [REPO_ROOT / "backend" / path for path in SOURCE_PATH.findall(line)]
            classes = set(BACKTICKED_SETTINGS.findall(line)) - {"BaseSettings"}
            if not modules or not classes:
                continue
            defined = set().union(*(_defined_in(module) for module in modules if module.exists()))
            wrong += [f"{page.relative_to(REPO_ROOT)}:{number}: {name}" for name in sorted(classes - defined)]

    assert not wrong, "\n".join(wrong)


def _settings_class(name: str) -> type[BaseSettings]:
    for path in SRC_ROOT.rglob("*.py"):
        if name in _defined_in(path):
            module = ".".join(path.relative_to(SRC_ROOT.parent).with_suffix("").parts)
            found = getattr(importlib.import_module(module), name)
            assert isinstance(found, type) and issubclass(found, BaseSettings), name

            return found

    raise LookupError(name)


def test_every_setting_a_row_of_the_settings_table_names_is_on_that_class():
    page = REPO_ROOT / "docs" / "user-guide" / "configuration" / "settings-classes.md"
    rows = [found.groups() for found in map(TABLE_ROW.match, page.read_text().splitlines()) if found]

    assert rows
    wrong = []
    for name, covers in rows:
        settings_class = _settings_class(name)
        wrong += [
            f"{name}: {field}"
            for field in BACKTICKED_FIELD.findall(covers)
            if "*" not in field
            and field not in settings_class.model_fields
            and not isinstance(inspect.getattr_static(settings_class, field, None), property)
        ]

    assert not wrong, "\n".join(wrong)


def _bases(source: str) -> list[str]:
    (settings,) = [node for node in ast.walk(ast.parse(source)) if isinstance(node, ast.ClassDef) and node.name == "Settings"]

    return [base.id for base in settings.bases if isinstance(base, ast.Name)]


def test_the_settings_page_composes_settings_as_the_wiring_does():
    page = (REPO_ROOT / "docs" / "user-guide" / "configuration" / "settings-classes.md").read_text()
    sample = page.split("```python\n# src/wiring/settings.py", 1)[1].split("\n", 1)[1].split("```", 1)[0]

    assert _bases(sample) == _bases((SRC_ROOT / "wiring" / "settings.py").read_text())


def test_the_default_tier_name_is_said_to_be_on_the_class_that_has_it():
    assert "DEFAULT_TIER_NAME" in _settings_class("TierSettings").model_fields
    for page in ("docs/user-guide/configuration/settings-classes.md", "docs/user-guide/admin-panel/configuration.md"):
        lines = [line for line in (REPO_ROOT / page).read_text().splitlines() if "`DEFAULT_TIER_NAME`" in line]
        assert lines, page
        assert all("`TierSettings`" in line for line in lines), (page, lines)
