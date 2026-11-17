"""The developer CLI this repository used to ship, as the scans that keep it gone read it.

Every needle is assembled from pieces, so the files that hold them never match themselves.
"""

import re
import subprocess
from collections.abc import Iterator
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

OLD_COMMAND = "b" + "p"

RUNS_OLD_COMMAND = re.compile(rf"\b{OLD_COMMAND} (?:deploy|env)\b|`{OLD_COMMAND}`")
"""A line that runs the old command, or names it in code."""


def tracked_text() -> Iterator[tuple[str, str]]:
    """Every file git tracks or would add, that reads as UTF-8, by its path from the root, with its text."""
    listed = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    for name in filter(None, listed.stdout.split("\0")):
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
