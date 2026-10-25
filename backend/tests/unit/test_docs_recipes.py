"""The documented commands that only work from a particular place.

Generating the first revision is the one autogenerate that has to run against a database
with nothing in it: against a database that already carries the schema, alembic finds no
difference and writes a revision whose ``upgrade()`` is ``pass``. Later revisions are the
opposite, and run against the database you serve, so this holds the baseline only.

``docker compose`` is the other one: the compose file the CLI writes lands at the
repository root, so a block that walks into ``backend/`` first gets ``no configuration
file provided``.

It reads fenced blocks, so a command written into a sentence is not covered.
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
DOCS_ROOT = REPO_ROOT / "docs"

FENCED_BLOCK = re.compile(r"```(?:bash|sh|console)\n(.*?)```", re.DOTALL)
GENERATES_A_BASELINE = re.compile(r"alembic revision --autogenerate[^\n]*-m\s+[\"']?baseline")

WALKS_INTO_THE_BACKEND = re.compile(r"^cd\s+[\w./-]*backend/?$")
WALKS_SOMEWHERE_ELSE = re.compile(r"^cd\s+[\w./-]+$")
RUNS_COMPOSE = re.compile(r"\bdocker compose\b")


def _documented_blocks() -> list[tuple[Path, str]]:
    """Every fenced block in the documentation and the README, with the page it is on."""
    pages = [*sorted(DOCS_ROOT.rglob("*.md")), REPO_ROOT / "README.md"]

    return [(page.relative_to(REPO_ROOT), block) for page in pages for block in FENCED_BLOCK.findall(page.read_text())]


def _compose_run_from_the_backend(block: str) -> bool:
    """Whether the block is in ``backend/`` by the time it runs ``docker compose``.

    Commands joined with ``&&`` are read in order, so the ``cd ..`` that a block walks
    back out with counts before the command beside it.
    """
    in_the_backend = False
    for segment in (part.strip() for line in block.splitlines() for part in line.split("&&")):
        if WALKS_INTO_THE_BACKEND.match(segment):
            in_the_backend = True
        elif WALKS_SOMEWHERE_ELSE.match(segment):
            in_the_backend = False
        elif in_the_backend and RUNS_COMPOSE.search(segment):
            return True

    return False


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


def test_no_documented_stack_is_brought_up_from_the_backend():
    """``cd backend`` then ``docker compose up`` was how four pages told a reader to start."""
    blocks = _documented_blocks()

    assert blocks, "no fenced block found, which is itself a change worth reading"
    assert sorted({str(page) for page, block in blocks if _compose_run_from_the_backend(block)}) == []


def test_the_sweep_reads_the_blocks_it_claims_to():
    """A block the sweep cannot see, or a walk it cannot follow, would make it vacuous."""
    pages = {str(page) for page, block in _documented_blocks() if RUNS_COMPOSE.search(block)}

    assert "README.md" in pages
    assert "docs/getting-started/installation.md" in pages
    assert _compose_run_from_the_backend("cd backend\ndocker compose up")
    assert not _compose_run_from_the_backend("cd backend\ncd .. && docker compose up")
