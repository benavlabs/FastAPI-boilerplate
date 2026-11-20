"""CI verifies every set `fastro blueprint verify` builds, one job each."""

from pathlib import Path
from typing import Any

import yaml
from fastro.engine import blueprint
from fastro.tools import installed_version
from fastro.verify import verify_sets

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "tests.yml"
TESTING = REPO_ROOT / "docs" / "user-guide" / "testing.md"

VERIFY = "uv run --no-sync fastro blueprint verify ${{ matrix.preset }}"


def _job() -> dict[str, Any]:
    jobs: dict[str, dict[str, Any]] = yaml.safe_load(WORKFLOW.read_text())["jobs"]
    (job,) = [job for job in jobs.values() if any(step.get("run") == VERIFY for step in job.get("steps", []))]

    return job


def _catalog() -> blueprint.Blueprint:
    return blueprint.load("blueprint.toml", (REPO_ROOT / "blueprint.toml").read_text(), installed_version())


def test_the_ci_matrix_is_every_set_verify_builds():
    assert set(_job()["strategy"]["matrix"]) == {"preset"}
    assert sorted(_job()["strategy"]["matrix"]["preset"]) == sorted(verify_sets(_catalog()))


def test_one_sets_failure_leaves_the_others_running():
    assert _job()["strategy"]["fail-fast"] is False


def test_a_failed_verify_fails_the_job():
    job = _job()
    (step,) = [step for step in job["steps"] if step.get("run") == VERIFY]

    assert not {"if", "continue-on-error"} & (set(job) | set(step))


def test_the_testing_guide_says_ci_verifies_every_set():
    section = " ".join(TESTING.read_text().split("## Continuous Integration", 1)[1].split("\n## ", 1)[0].split())

    assert "`fastro blueprint verify`" in section
    assert "`[verify.sets]`" in section
    assert "`everything`" in section
    assert ("presets" in section) is _catalog().verify.include_presets
