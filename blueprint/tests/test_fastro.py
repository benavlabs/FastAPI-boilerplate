"""What the fastro the repository root installs gives the people who work on the blueprint."""

import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _fastro(*arguments: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, "-m", "fastro", *arguments], cwd=cwd, capture_output=True, text=True, check=False)


def _tree(destination: Path) -> Path:
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


def test_plain_sync_regenerates_what_the_check_compares(tmp_path: Path):
    """CONTRIBUTING.md sends a failed `fastro sync --check` to `fastro sync`."""
    tree = _tree(tmp_path / "blueprint")
    wiring = tree / tomllib.loads((tree / "blueprint.toml").read_text())["wiring"][0]["path"]
    generated = wiring.read_text()
    wiring.write_text(generated + "\nedited = True\n")

    assert _fastro("sync", "--check", cwd=tree).returncode == 1

    synced = _fastro("sync", cwd=tree)

    assert synced.returncode == 0, synced.stderr
    assert _fastro("sync", "--check", cwd=tree).returncode == 0
