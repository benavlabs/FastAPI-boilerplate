"""The pre-commit hooks the development guide describes, run the way a contributor runs them."""

import os
import re
import shutil
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


def _git(*arguments: str, cwd: Path) -> str:
    settings = ["user.name=test", "user.email=test@example.com", "commit.gpgsign=false", "core.hooksPath=/dev/null"]
    command = ["git", *(part for setting in settings for part in ("-c", setting)), *arguments]

    return subprocess.run(command, cwd=cwd, capture_output=True, text=True, check=True).stdout


def _tracked_copy(destination: Path) -> Path:
    """A git repository holding the files git tracks here and nothing else, as fastro reads the blueprint."""
    deleted = set(_git("ls-files", "-z", "--deleted", cwd=REPO_ROOT).split("\0"))
    for name in filter(None, _git("ls-files", "-z", cwd=REPO_ROOT).split("\0")):
        if name not in deleted:
            (destination / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(REPO_ROOT / name, destination / name)
    _git("init", "-q", cwd=destination)
    _git("add", "-A", cwd=destination)
    _git("commit", "-q", "-m", "tracked", cwd=destination)

    return destination


def test_the_unit_test_hook_passes_without_docker(tmp_path: Path):
    """Every unit test that starts a container skips when Docker can't be reached, and the rest pass.

    The hook runs over the files git tracks, beside an untracked virtualenv that imports two
    distributions only one feature each declares, as an installed package does, and a feature's
    module: no untracked folder, a venv, a build or a cache, can change what it says."""
    directory, arguments = _unit_test_hook()
    copy = _tracked_copy(tmp_path / "blueprint")
    stray = copy / directory / ".venv" / "lib" / "python3.11" / "site-packages" / "stray.py"
    stray.parent.mkdir(parents=True)
    stray.write_text("import itsdangerous\nimport user_agents\nimport src.modules.user\n")
    unreachable = {name: value for name, value in os.environ.items() if not name.startswith("TESTCONTAINERS")}
    unreachable |= {"HOME": str(tmp_path), "DOCKER_HOST": "tcp://127.0.0.1:1"}

    assert stray.is_file() and not _git("ls-files", str(stray.relative_to(copy)), cwd=copy)

    run = subprocess.run(
        [sys.executable, "-m", "pytest", *arguments, "-q", "-n", "auto", "-p", "no:cacheprovider"],
        cwd=copy / directory,
        env=unreachable,
        capture_output=True,
        text=True,
        check=False,
    )

    assert run.returncode == 0, run.stdout[-4000:]
    assert re.search(r"\b[1-9]\d* skipped\b", run.stdout), run.stdout[-4000:]
