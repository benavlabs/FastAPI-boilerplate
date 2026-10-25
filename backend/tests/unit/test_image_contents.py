"""What the image carries, for the commands the documentation runs inside a container.

Nothing in CI builds the image, so this reads the Dockerfile. A script the documentation
runs as ``docker compose exec api python -m scripts.<name>`` has to be in there: without
it the command answers ``No module named 'scripts'``.

The module form is also the only one that works in there. The container's working
directory is ``/app/src`` while the scripts are at ``/app/scripts``, so
``python scripts/<name>.py`` answers ``can't open file '/app/src/scripts/<name>.py'``.
"""

import re
from pathlib import Path

from tests.unit.test_docs_imports import LEFT_OUT_PATHS

REPO_ROOT = Path(__file__).resolve().parents[3]
DOCKERFILE = REPO_ROOT / "backend" / "Dockerfile"
DOCS_ROOT = REPO_ROOT / "docs"
SCRIPTS = REPO_ROOT / "backend" / "scripts"

BASE_STAGE = re.compile(r"^FROM .*? AS base$(.*?)^FROM ", re.DOTALL | re.MULTILINE)
RUN_IN_A_CONTAINER = re.compile(r"docker compose (?:exec|run)[^\n`]*python -m (scripts\.\w+)")
A_PATH_IN_A_CONTAINER = re.compile(r"docker compose (?:exec|run)[^\n`]*python +(scripts/[\w.]+)")


def _base_stage() -> str:
    """The stage every other one builds on, so what it copies is in all of them."""
    found = BASE_STAGE.search(DOCKERFILE.read_text())
    assert found is not None, "no base stage in the Dockerfile"

    return found.group(1)


def test_the_image_carries_the_scripts_and_the_migrations():
    stage = _base_stage()

    assert "COPY backend/scripts ./scripts" in stage
    assert "COPY backend/migrations ./migrations" in stage
    assert "COPY backend/alembic.ini ." in stage


def test_alembic_finds_its_configuration_from_the_working_directory_the_stages_use():
    """``docker compose exec api alembic upgrade head`` runs from ``/app/src``, where there is none."""
    stage = _base_stage()

    assert "ENV ALEMBIC_CONFIG=/app/alembic.ini" in stage


def _carried_by_this_project(module: str) -> bool:
    """Whether this project still has the script, rather than having removed its feature.

    The documentation describes every feature, so a build without one still shows commands
    for scripts it no longer carries.
    """
    return f"backend/scripts/{module.split('.')[1]}.py" not in LEFT_OUT_PATHS


def test_every_script_the_docs_run_in_a_container_exists():
    """The module name in the documented command has to name a file the image copies."""
    documented = {
        module
        for page in DOCS_ROOT.rglob("*.md")
        for module in RUN_IN_A_CONTAINER.findall(page.read_text())
        if _carried_by_this_project(module)
    }

    assert documented, "no documented in-container script run found"
    assert [module for module in sorted(documented) if not (SCRIPTS / f"{module.split('.')[1]}.py").exists()] == []


def test_no_documented_container_command_runs_a_script_by_path():
    """``/app/src`` is the working directory in there, and the scripts are at ``/app/scripts``."""
    by_path = {
        f"{page.relative_to(DOCS_ROOT)}: {match}"
        for page in DOCS_ROOT.rglob("*.md")
        for match in A_PATH_IN_A_CONTAINER.findall(page.read_text())
    }

    assert sorted(by_path) == []
