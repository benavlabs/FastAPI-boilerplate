"""A generated project names itself: `APP_NAME` defaults to the name it was generated with.

The overlay renders `src/infrastructure/config/project.py` with `project.name` (spec 6.2), and
this repository, which has no such file, keeps its own default.
"""

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from jinja2 import Environment, FileSystemLoader, StrictUndefined

REPO_ROOT = Path(__file__).resolve().parents[2]
OVERLAY = REPO_ROOT / "blueprint" / "overlay"
PROJECT_MODULE = Path("backend/src/infrastructure/config/project.py")
TEMPLATE = PROJECT_MODULE.with_name(PROJECT_MODULE.name + ".j2")
ENV_EXAMPLE = REPO_ROOT / "backend" / ".env.example"
VARIABLES_PAGE = REPO_ROOT / "docs" / "user-guide" / "configuration" / "environment-variables.md"
BLUEPRINT_DEFAULT = "FastAPI Boilerplate"


def _rendered(name: str) -> str:
    environment = Environment(loader=FileSystemLoader(OVERLAY), undefined=StrictUndefined, keep_trailing_newline=True)

    return environment.get_template(TEMPLATE.as_posix()).render(project={"name": name, "slug": name.lower()})


def _tracked_backend_source(destination: Path) -> None:
    listed = subprocess.run(
        ["git", "ls-files", "-z", "backend/src"], cwd=REPO_ROOT, capture_output=True, text=True, check=True
    ).stdout
    for name in filter(None, listed.split("\0")):
        if (REPO_ROOT / name).is_file():
            (destination / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(REPO_ROOT / name, destination / name)


def _app_name(backend: Path) -> str:
    environment = {name: value for name, value in os.environ.items() if name != "APP_NAME"}
    shown = subprocess.run(
        [sys.executable, "-c", "from src.infrastructure.config.base import AppSettings; print(AppSettings().APP_NAME)"],
        cwd=backend,
        env={**environment, "PYTEST_VERSION": "1"},
        capture_output=True,
        text=True,
        check=True,
    )

    return shown.stdout.strip()


@pytest.mark.parametrize("name", ["acme-api", "Acme.API_2", "x"])
def test_a_generated_project_is_named_what_it_was_generated_as(tmp_path: Path, name: str):
    _tracked_backend_source(tmp_path)
    (tmp_path / PROJECT_MODULE).write_text(_rendered(name))

    assert _app_name(tmp_path / "backend") == name


def test_a_project_module_that_cannot_import_is_not_taken_for_a_missing_one(tmp_path: Path):
    _tracked_backend_source(tmp_path)
    (tmp_path / PROJECT_MODULE).write_text("import not_a_module_anywhere\n" + _rendered("acme-api"))

    with pytest.raises(subprocess.CalledProcessError) as refused:
        _app_name(tmp_path / "backend")

    assert "not_a_module_anywhere" in refused.value.stderr


def test_this_repository_keeps_its_own_name():
    assert not (REPO_ROOT / PROJECT_MODULE).exists()
    assert _app_name(REPO_ROOT / "backend") == BLUEPRINT_DEFAULT


def test_the_example_leaves_the_name_to_the_project():
    """A project copies `.env.example` to `.env`, so a value there would win over its own name."""
    assert not re.search(r"^APP_NAME=", ENV_EXAMPLE.read_text(), re.M)
    assert re.search(r"^# APP_NAME=", ENV_EXAMPLE.read_text(), re.M)


def test_the_variables_page_gives_the_project_its_own_name():
    page = VARIABLES_PAGE.read_text()

    assert not re.search(r"^APP_NAME=", page, re.M)
    assert re.search(r"^# APP_NAME=", page, re.M)
    assert f"`{PROJECT_MODULE.relative_to('backend').as_posix()}`" in page
    assert f'"{BLUEPRINT_DEFAULT}"' in page
