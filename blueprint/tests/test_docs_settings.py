"""The settings pattern the docs show is the one the project's settings use."""

import ast
import importlib
import re
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest
from retired import REPO_ROOT, shown_pages

BASE = REPO_ROOT / "backend" / "src" / "infrastructure" / "config" / "base.py"
SETTINGS_PAGE = REPO_ROOT / "docs" / "user-guide" / "configuration" / "settings-classes.md"
BASE_IMPORTS = {"from src.infrastructure.config.base import EnvSettings"}
FENCED_PYTHON = re.compile(r"^\s*```python\n(.*?)^\s*```", re.M | re.S)


def _python_blocks() -> list[tuple[str, str]]:
    return [(name, block) for name, text in shown_pages() for block in FENCED_PYTHON.findall(text)]


def test_the_pages_show_settings_classes():
    """The rules below have code to read."""
    assert any("EnvSettings" in block for _, block in _python_blocks())


def test_no_block_reads_a_setting_through_the_import_time_loader():
    found = [name for name, block in _python_blocks() if re.search(r"=\s*config\(\s*[\"']", block)]

    assert found == []


def test_no_block_derives_a_settings_group_from_basesettings_directly():
    found = [name for name, block in _python_blocks() if re.search(r"^\s*class \w+\(BaseSettings\):", block, re.M)]

    assert found == []


def test_the_base_the_page_names_is_where_it_says():
    defined = {node.name for node in ast.parse(BASE.read_text()).body if isinstance(node, ast.ClassDef)}

    assert "`EnvSettings` in `src/infrastructure/config/base.py`" in SETTINGS_PAGE.read_text()
    assert "EnvSettings" in defined


@contextmanager
def _backend_importable() -> Iterator[None]:
    sys.path.insert(0, str(REPO_ROOT / "backend"))
    try:
        yield
    finally:
        sys.path.remove(str(REPO_ROOT / "backend"))


def _base() -> Any:
    """`src.infrastructure.config.base`, imported from the backend."""
    with _backend_importable():
        return importlib.import_module("src.infrastructure.config.base")


def _section(heading: str) -> str:
    text = SETTINGS_PAGE.read_text()
    assert heading in text, heading

    return text.split(heading, 1)[1].split("\n## ", 1)[0]


def test_the_page_s_own_example_reads_a_value_set_after_it_is_defined(monkeypatch: pytest.MonkeyPatch):
    block = FENCED_PYTHON.findall(_section("### Basic Custom Group"))[0]
    example = block.split("\nclass Settings(", 1)[0]
    scope: dict[str, Any] = {}
    with _backend_importable():
        exec(compile(example, "settings-classes.md", "exec"), scope)

    assert "from src.infrastructure.config.base import EnvSettings" in example
    assert scope["StorageSettings"].__mro__[1] is _base().EnvSettings

    monkeypatch.setenv("STORAGE_BACKEND", "s3")

    assert scope["StorageSettings"]().STORAGE_BACKEND == "s3"


def test_the_validator_the_page_shows_is_the_one_the_database_settings_use():
    anatomy = _section("## Anatomy of a Settings Group")
    database = next(
        node for node in ast.parse(BASE.read_text()).body if isinstance(node, ast.ClassDef) and node.name == "DatabaseSettings"
    )
    before = [
        method.name
        for method in database.body
        if isinstance(method, ast.FunctionDef)
        and any("model_validator(mode='before')" in ast.unparse(decorator) for decorator in method.decorator_list)
    ]

    assert before == ["_tables_follow_the_environment"]
    assert '@model_validator(mode="before")' in anatomy and "def _tables_follow_the_environment" in anatomy


def test_the_file_reads_the_way_the_page_says(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    key_points = _section("## Anatomy of a Settings Group")
    stored = tmp_path / ".env"
    stored.write_text("APP_NAME=ab${HOME}cd # kept\n")
    monkeypatch.delenv("APP_NAME", raising=False)

    assert "no `${...}` expansion" in key_points and "a `#` is part of the value" in key_points
    assert _base().AppSettings(_env_file=stored).APP_NAME == "ab${HOME}cd # kept"


def test_every_block_that_imports_the_base_takes_it_from_where_the_mixins_do():
    imports = [line.strip() for _, block in _python_blocks() for line in block.splitlines() if "import EnvSettings" in line]

    assert imports
    assert [line for line in imports if line.split("#", 1)[0].strip() not in BASE_IMPORTS] == []


def test_a_flag_and_a_number_read_the_way_the_page_says(monkeypatch: pytest.MonkeyPatch):
    key_points = _section("## Anatomy of a Settings Group")

    class Probe(_base().EnvSettings):  # type: ignore[misc,name-defined]
        DOC_FLAG: bool = False
        DOC_COUNT: int = 0

    assert "`true`, `false`, `1` or `0`" in key_points and "`int()`" in key_points
    for name, written in (("DOC_FLAG", "yes"), ("DOC_COUNT", "1.0")):
        monkeypatch.setenv(name, written)
        with pytest.raises(ValueError):
            Probe()
        monkeypatch.delenv(name)
