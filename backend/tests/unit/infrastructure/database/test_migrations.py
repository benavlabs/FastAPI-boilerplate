"""What ``alembic`` does when the project has no revisions yet.

The commands run against a copy of ``migrations/`` with its own empty versions
directory, so these hold whether or not this repository has a baseline committed.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[4]


def _alembic(tmp_path: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    """Run alembic against a copy of the project's migrations with no revisions in it."""
    migrations = tmp_path / "migrations"
    migrations.mkdir()
    (migrations / "versions").mkdir()
    for name in ("env.py", "script.py.mako"):
        shutil.copy(BACKEND / "migrations" / name, migrations / name)

    config = (
        (BACKEND / "alembic.ini")
        .read_text()
        .replace("script_location = %(here)s/migrations", f"script_location = {migrations}")
    )
    (tmp_path / "alembic.ini").write_text(config)

    return subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(tmp_path / "alembic.ini"), *arguments],
        cwd=BACKEND,
        env={**os.environ, "PYTHONPATH": str(BACKEND)},
        capture_output=True,
        text=True,
    )


def test_an_upgrade_with_no_revisions_is_refused(tmp_path: Path):
    """It would create ``alembic_version`` alone, exit 0, and leave the app with no schema."""
    result = _alembic(tmp_path, "upgrade", "head")

    assert result.returncode != 0
    assert "No migration revisions exist" in result.stderr + result.stdout


def test_generating_the_first_revision_is_let_through(tmp_path: Path):
    """The one command that has to run with an empty history.

    It reaches the database, which this test doesn't provide, so the refusal above is
    what must not appear.
    """
    result = _alembic(tmp_path, "revision", "--autogenerate", "-m", "baseline")

    assert "No migration revisions exist" not in result.stderr + result.stdout
