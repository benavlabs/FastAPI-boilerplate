"""What a source tarball carries, which is whatever `git archive` writes.

GitHub builds a release's tarball the same way, so a path marked `export-ignore` is one a
download doesn't have. What's left out is the blueprint's own: the documentation site, the
removal drill and the issue templates are things to read or run in this repository, not things
a reader builds the project from.
"""

import io
import subprocess
import tarfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]

LEFT_OUT = (".github/ISSUE_TEMPLATE/", "docs/", "tools/", "zensical.toml")
"""The paths `.gitattributes` keeps out of the tarball."""

CARRIED = ("README.md", "backend/Dockerfile", "backend/pyproject.toml", "backend/src/interfaces/main.py")
"""A few a reader could not build the project without, so the archive is read, not assumed.

The compose file is not among them: `.gitignore` keeps it out, because the deploy generator
writes it."""


def _archived() -> set[str]:
    """Every path `git archive` writes for the current commit.

    The attributes are read from the working tree rather than from `HEAD`, so a `.gitattributes`
    that isn't committed yet still counts and the answer doesn't wait for the commit.
    """
    written = subprocess.run(
        ["git", "archive", "--worktree-attributes", "--format=tar", "HEAD"],
        cwd=REPO_ROOT,
        capture_output=True,
        check=True,
    )
    with tarfile.open(fileobj=io.BytesIO(written.stdout)) as archive:
        return {member.name for member in archive.getmembers()}


def test_the_tarball_leaves_out_what_only_this_repository_needs():
    archived = _archived()

    assert {name for name in archived for path in LEFT_OUT if name.startswith(path.rstrip("/"))} == set()


def test_the_tarball_carries_what_the_project_is_built_from():
    """The other direction, and the proof that the archive was read at all."""
    archived = _archived()

    assert archived
    assert set(CARRIED) <= archived


def test_every_path_kept_out_is_one_this_repository_has():
    """A path that moved would be ignored silently, leaving the real one in the tarball."""
    for path in LEFT_OUT:
        assert (REPO_ROOT / path).exists(), path
