"""Every link between the docs pages lands on a page, and on a heading when it names one.

zensical builds with `toc` and no custom slugify, so a heading's id is Python-Markdown's default
slug of its text, or the `{#id}` it sets.
"""

import re
import tomllib
import unicodedata
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DOCS = REPO_ROOT / "docs"
SITE = tomllib.loads((REPO_ROOT / "zensical.toml").read_text())["project"]

LINK = re.compile(r"!?\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")


def _pages() -> list[Path]:
    return sorted(DOCS.rglob("*.md"))


def _outside_fences(text: str) -> Iterator[tuple[int, str]]:
    fenced = False
    for number, line in enumerate(text.splitlines(), 1):
        if line.lstrip().startswith("```"):
            fenced = not fenced
        elif not fenced:
            yield number, line


def slug(heading: str) -> str:
    """Python-Markdown's default `toc` slug of a heading's text."""
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", heading)
    text = re.sub(r"[`*]", "", text)
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^\w\s-]", "", text).strip().lower()

    return re.sub(r"[-\s]+", "-", text)


def _anchors(page: Path) -> set[str]:
    anchors = set()
    for _, line in _outside_fences(page.read_text()):
        heading = re.match(r"^#{1,6}\s+(.*?)\s*$", line)
        if not heading:
            continue
        given = re.search(r"\{[^}]*#([\w-]+)[^}]*\}\s*$", heading[1])
        anchors.add(given[1] if given else slug(heading[1]))

    return anchors


def _links() -> list[tuple[str, str]]:
    return [
        (f"{page.relative_to(DOCS)}:{number}", target)
        for page in _pages()
        for number, line in _outside_fences(page.read_text())
        for target in LINK.findall(re.sub(r"`[^`]*`", "", line))
        if not re.match(r"^[a-z]+:", target)
    ]


def _resolved(where: str, target: str) -> tuple[Path, str]:
    page = DOCS / where.rsplit(":", 1)[0]
    path, _, anchor = target.partition("#")

    return ((page.parent / path).resolve() if path else page), anchor


def test_the_docs_link_to_one_another():
    """The rule below has links to read."""
    assert len(_links()) > 50


@pytest.mark.parametrize(("where", "target"), _links(), ids=[f"{where} {target}" for where, target in _links()])
def test_every_relative_link_lands_on_a_file_and_a_heading(where: str, target: str):
    path, anchor = _resolved(where, target)

    assert path.is_file(), (where, target)
    if anchor and path.suffix == ".md":
        assert anchor in _anchors(path), (where, target, sorted(_anchors(path)))


def _nav_pages(entries: Any) -> Iterator[str]:
    if isinstance(entries, str):
        yield entries
    elif isinstance(entries, list):
        for entry in entries:
            yield from _nav_pages(entry)
    elif isinstance(entries, dict):
        for value in entries.values():
            yield from _nav_pages(value)


def test_every_page_is_in_the_nav_and_every_nav_entry_is_a_page():
    listed = sorted(_nav_pages(SITE["nav"]))

    assert sorted(set(listed)) == listed, "a page listed twice"
    assert listed == sorted(page.relative_to(DOCS).as_posix() for page in _pages())


def test_every_redirect_leaves_a_page_that_is_gone_for_one_that_is_there():
    redirects = SITE["plugins"]["redirects"]["redirect_maps"]

    assert redirects == {f"cli/{page}.md": "user-guide/fastro.md" for page in ("index", "commands", "plugins")}
    for gone, there in redirects.items():
        assert not (DOCS / gone).exists(), gone
        assert (DOCS / there).is_file(), there


@pytest.mark.parametrize(
    ("heading", "expected"),
    [
        ("Authentication & Security", "authentication-security"),
        ("Writing the compose files: `fastro make deploy`", "writing-the-compose-files-fastro-make-deploy"),
        ("What `fastro make deploy local` Writes", "what-fastro-make-deploy-local-writes"),
        ("Neon (Serverless Postgres)", "neon-serverless-postgres"),
        ("Generating a Strong `SECRET_KEY`", "generating-a-strong-secret_key"),
        ("Café Résumé", "cafe-resume"),
    ],
)
def test_the_slug_is_the_one_toc_writes(heading: str, expected: str):
    assert slug(heading) == expected
