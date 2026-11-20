import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

FastroRunner = Callable[..., subprocess.CompletedProcess[str]]


@pytest.fixture
def tracked_tree(tmp_path: Path) -> Path:
    """A copy of every file git tracks or would track, so a test can change it freely."""
    destination = tmp_path / "blueprint"
    listed = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    for name in filter(None, listed.split("\0")):
        source = REPO_ROOT / name
        if source.is_file():
            (destination / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination / name)

    return destination


@pytest.fixture
def fastro() -> FastroRunner:
    """Run the fastro the repository root installs, in a directory of the caller's choosing."""

    def run(*arguments: str, cwd: Path) -> subprocess.CompletedProcess[str]:
        command = [sys.executable, "-m", "fastro", *arguments]
        return subprocess.run(command, cwd=cwd, capture_output=True, text=True, check=False)

    return run
