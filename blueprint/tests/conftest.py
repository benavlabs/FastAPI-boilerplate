import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import pytest
from tracked import REPO_ROOT, tracked_names

FastroRunner = Callable[..., subprocess.CompletedProcess[str]]


@pytest.fixture
def tracked_tree(tmp_path: Path) -> Path:
    """A copy of every file git tracks and still has, so a test can change it freely."""
    destination = tmp_path / "blueprint"
    for name in tracked_names():
        (destination / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO_ROOT / name, destination / name)

    return destination


@pytest.fixture
def fastro() -> FastroRunner:
    """Run the fastro the repository root installs, in a directory of the caller's choosing."""

    def run(*arguments: str, cwd: Path) -> subprocess.CompletedProcess[str]:
        command = [sys.executable, "-m", "fastro", *arguments]
        return subprocess.run(command, cwd=cwd, capture_output=True, text=True, check=False)

    return run
