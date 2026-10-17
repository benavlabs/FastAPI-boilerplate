"""The documented commands that only work against a particular database.

Generating the first revision is the one autogenerate that has to run against a database
with nothing in it: against a database that already carries the schema, alembic finds no
difference and writes a revision whose ``upgrade()`` is ``pass``. Later revisions are the
opposite, and run against the database you serve, so this holds the baseline only.

It reads fenced blocks, so a command written into a sentence is not covered.
"""

import re
from pathlib import Path

DOCS_ROOT = Path(__file__).resolve().parents[3] / "docs"

FENCED_BLOCK = re.compile(r"```(?:bash|sh|console)\n(.*?)```", re.DOTALL)
GENERATES_A_BASELINE = re.compile(r"alembic revision --autogenerate[^\n]*-m\s+[\"']?baseline")


def _blocks_generating_a_baseline() -> list[tuple[Path, str]]:
    found = []
    for page in sorted(DOCS_ROOT.rglob("*.md")):
        for block in FENCED_BLOCK.findall(page.read_text()):
            if GENERATES_A_BASELINE.search(block):
                found.append((page.relative_to(DOCS_ROOT), block))

    return found


def test_every_documented_baseline_names_the_database_it_generates_against():
    """Without an overridden database the reader generates an empty baseline from their dev stack."""
    blocks = _blocks_generating_a_baseline()

    assert blocks, "no documented baseline recipe found, which is itself a change worth reading"
    assert [page for page, block in blocks if "POSTGRES_DB=" not in block] == []
