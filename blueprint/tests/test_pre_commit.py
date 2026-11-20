"""The pre-commit hooks the development guide describes, run the way a contributor runs them."""

import os
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _unit_test_hook() -> tuple[str, list[str]]:
    """The directory the unit test hook runs in, and the arguments it gives pytest."""
    config = (REPO_ROOT / ".pre-commit-config.yaml").read_text()
    entry = r" +entry: bash -c 'cd (\S+) && uv run --no-sync pytest(.*)'\n"
    found = re.search(rf"- id: unit_test\n(?: +[\w-]+:.*\n)*?{entry}", config)
    assert found, config

    return found[1], found[2].split()


def test_the_unit_test_hook_passes_without_docker(tmp_path: Path):
    """Every unit test that starts a container skips when Docker can't be reached, and the rest pass."""
    directory, arguments = _unit_test_hook()
    unreachable = {name: value for name, value in os.environ.items() if not name.startswith("TESTCONTAINERS")}
    unreachable |= {"HOME": str(tmp_path), "DOCKER_HOST": "tcp://127.0.0.1:1"}

    run = subprocess.run(
        [sys.executable, "-m", "pytest", *arguments, "-q", "-n", "auto", "-p", "no:cacheprovider"],
        cwd=REPO_ROOT / directory,
        env=unreachable,
        capture_output=True,
        text=True,
        check=False,
    )

    assert run.returncode == 0, run.stdout[-4000:]
    assert re.search(r"\b[1-9]\d* skipped\b", run.stdout), run.stdout[-4000:]
