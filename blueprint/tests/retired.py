"""The developer CLI this repository used to ship, and the drill that built the repository
without each feature, as the scans that keep them gone read them.

Every needle is assembled from pieces, so the files that hold them never match themselves.
"""

import re
from collections.abc import Iterator

from tracked import REPO_ROOT, tracked_names

OLD_COMMAND = "b" + "p"

RUNS_OLD_COMMAND = re.compile(rf"\b{OLD_COMMAND} (?:deploy|env)\b|`{OLD_COMMAND}`")
"""A line that runs the old command, or names it in code."""

NAMES_OLD_COMMAND = re.compile(rf"{RUNS_OLD_COMMAND.pattern}|\brun {OLD_COMMAND}\b|\b{OLD_COMMAND}(?:<[^>]*>)? CLI\b")
"""A line that runs the old command, names it in code, or calls it a CLI."""

SAYS_OLD_COMMAND_EXITS = re.compile(rf"^`{OLD_COMMAND} deploy generate` exits 2 too, in a project made before fastro\.$")
"""The one line a reader sees that names the old command: the fastro page saying it is refused."""

OLD_PACKAGE = "c" + "li"

NAMES_OLD_PACKAGE = re.compile(rf"(?<![\w.-]){OLD_PACKAGE}(?![\w-])|\bboilerplate-{OLD_PACKAGE}\b")
"""The old package as a word: its folder, a path into it, its module, its distribution. Not
`redis-cli`, `fastro.cli` or "CLI"."""

OLD_DRILL = "removal" + "_drill"

NAMES_OLD_DRILL = re.compile(rf"{OLD_DRILL}|\b{OLD_COMMAND}-and-fastro\b")
"""The drill's module, its test, or the directory it left out of the copies it built."""


def tracked_text() -> Iterator[tuple[str, str]]:
    """Every file git tracks and still has, that reads as UTF-8, by its path from the root, with its text."""
    for name in sorted(tracked_names()):
        path = REPO_ROOT / name
        if not path.is_file():
            continue
        try:
            yield name, path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue


def shown_pages() -> Iterator[tuple[str, str]]:
    """The Markdown a reader sees: the README and the docs, the changelog's history aside."""
    for name, text in tracked_text():
        if name == "README.md" or (name.startswith("docs/") and name.endswith(".md") and name != "docs/changelog.md"):
            yield name, text
