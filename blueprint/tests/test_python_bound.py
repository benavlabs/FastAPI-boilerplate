"""The Pythons the project allows, and CI running on the oldest and the newest of them."""

import tomllib
from pathlib import Path
from typing import Any

import pytest
import yaml
from packaging.specifiers import SpecifierSet

REPO_ROOT = Path(__file__).resolve().parents[2]
PYPROJECTS = [REPO_ROOT / "pyproject.toml", REPO_ROOT / "backend" / "pyproject.toml"]
WORKFLOWS = REPO_ROOT / ".github" / "workflows"
BLUEPRINT = REPO_ROOT / "blueprint.toml"
PROJECT_WORKFLOW = REPO_ROOT / "blueprint" / "overlay" / ".github" / "workflows" / "ci.yml.j2"
INSTALLATION = REPO_ROOT / "docs" / "getting-started" / "installation.md"
TESTING = REPO_ROOT / "docs" / "user-guide" / "testing.md"

MINORS = range(0, 100)

SUITES = [
    "cd backend && uv run --no-sync pytest",
    "uv run --no-sync pytest blueprint/tests",
]


def _allowed(pyproject: Path) -> SpecifierSet:
    return SpecifierSet(tomllib.loads(pyproject.read_text())["project"]["requires-python"])


def _minors() -> list[str]:
    allowed = _allowed(PYPROJECTS[0])

    return [f"3.{minor}" for minor in MINORS if f"3.{minor}.0" in allowed]


def _jobs() -> list[dict[str, Any]]:
    jobs: list[dict[str, Any]] = []
    for workflow in sorted(WORKFLOWS.glob("*.yml")):
        jobs.extend(yaml.safe_load(workflow.read_text())["jobs"].values())

    return jobs


def _runs(job: dict[str, Any]) -> list[str]:
    return [step["run"] for step in job.get("steps", []) if "run" in step]


def _jobs_on(python: str) -> list[list[str]]:
    return [
        _runs(job)
        for job in _jobs()
        if f"uv python install {python}" in _runs(job)
        and any(run.startswith("uv sync") and run.endswith(f"--python {python}") for run in _runs(job))
    ]


def test_the_workspace_and_the_backend_allow_the_same_pythons():
    """The backend is what a generated project is built from, so it has to carry the bound too."""
    assert _allowed(PYPROJECTS[0]) == _allowed(PYPROJECTS[1])


def test_the_allowed_pythons_stop_at_a_newest_one():
    """With no upper bound uv picks the newest Python it finds, one some dependency may not install on."""
    allowed = _allowed(PYPROJECTS[0])

    assert f"3.{MINORS[-1]}.0" not in allowed
    assert _minors() == [f"3.{minor}" for minor in range(int(_minors()[0][2:]), int(_minors()[-1][2:]) + 1)]


@pytest.mark.parametrize("end", [0, -1], ids=["oldest", "newest"])
def test_ci_runs_both_suites_on_the_oldest_and_the_newest_allowed_python(end: int):
    python = _minors()[end]

    assert any(set(SUITES) <= set(runs) for runs in _jobs_on(python)), python


def test_ci_verifies_a_generated_project_on_the_newest_allowed_python():
    """The only Python that job installs, so a generated project resolving its own has that one to pick."""
    newest = _minors()[-1]

    assert any(any(run.startswith("uv run --no-sync fastro blueprint verify ") for run in runs) for runs in _jobs_on(newest))


def test_nothing_ci_or_verify_runs_picks_a_python_with_uv_python():
    """The repo's workflows, a generated project's, and the environment every verify check runs in."""
    workflows = [*WORKFLOWS.glob("*.yml"), PROJECT_WORKFLOW]
    checks = tomllib.loads(BLUEPRINT.read_text()).get("checks", {})

    assert all("UV_PYTHON" not in workflow.read_text() for workflow in workflows)
    assert all("UV_PYTHON" not in check.get("env", {}) for check in checks.values())


def test_the_installation_guide_names_the_oldest_and_the_newest_allowed_python():
    """In the system requirements and in the prerequisites for running it on the host."""
    text = INSTALLATION.read_text()
    requirements = text.split("## System Requirements", 1)[1].split("\n## ", 1)[0]
    prerequisites = [section.split("\n### ", 1)[0] for section in text.split("### Prerequisites")[1:]]
    lines = [
        *[line for line in requirements.splitlines() if "**Python**" in line],
        *[line for section in prerequisites for line in section.splitlines() if line.startswith("1. **Python")],
    ]

    assert len(lines) == 2
    for line in lines:
        assert _minors()[0] in line, line
        assert _minors()[-1] in line, line


def test_the_testing_guide_says_ci_runs_on_the_oldest_and_the_newest_allowed_python():
    section = " ".join(TESTING.read_text().split("## Continuous Integration", 1)[1].split("\n## ", 1)[0].split())

    assert f"Python {_minors()[0]}" in section
    assert f"Python {_minors()[-1]}" in section
