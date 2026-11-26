"""What the fastro the repository root installs gives the people who work on the blueprint."""

import tomllib
from pathlib import Path

from conftest import FastroRunner

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_plain_sync_regenerates_what_the_check_compares(tracked_tree: Path, fastro: FastroRunner):
    """CONTRIBUTING.md sends a failed `fastro sync --check` to `fastro sync`."""
    tree = tracked_tree
    wiring = tree / tomllib.loads((tree / "blueprint.toml").read_text())["wiring"][0]["path"]
    generated = wiring.read_text()
    wiring.write_text(generated + "\nedited = True\n")

    assert fastro("sync", "--check", cwd=tree).returncode == 1

    synced = fastro("sync", cwd=tree)

    assert synced.returncode == 0, synced.stderr
    assert fastro("sync", "--check", cwd=tree).returncode == 0
