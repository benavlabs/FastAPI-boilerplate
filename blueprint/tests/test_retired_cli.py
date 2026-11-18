"""Nothing outside the history names the developer tool's old package or the command it shipped."""

import importlib.metadata
import re
from collections.abc import Iterator

import pytest
from fastro import compat
from retired import NAMES_OLD_COMMAND, NAMES_OLD_PACKAGE, OLD_COMMAND, OLD_PACKAGE, REPO_ROOT, tracked_text

NEEDLES = {"package": NAMES_OLD_PACKAGE, "command": NAMES_OLD_COMMAND}

STILL_CARRYING = {
    ("package", "docs/changelog.md"): "the history, for good",
    ("command", "docs/changelog.md"): "the history, for good",
    ("command", "docs/assets/build-cover.cjs"): "B5",
}
"""Which needle each exempted file carries, and the item that lifts the exemption."""

REDIRECTS = "[project.plugins.redirects.redirect_maps]"


def _lines(name: str, text: str) -> Iterator[tuple[int, str]]:
    """The numbered lines of a file, without the lines of `zensical.toml`'s redirect map."""
    inside = False
    for number, line in enumerate(text.splitlines(), 1):
        if name == "zensical.toml" and line.startswith("["):
            inside = line.strip() == REDIRECTS
        if not inside:
            yield number, line


def _hits() -> dict[tuple[str, str], list[str]]:
    hits: dict[tuple[str, str], list[str]] = {}
    for name, text in tracked_text():
        for number, line in _lines(name, text):
            for needle, pattern in NEEDLES.items():
                if pattern.search(line):
                    hits.setdefault((needle, name), []).append(f"{name}:{number}: {line.strip()}")

    return hits


def test_no_file_names_the_old_package_or_its_command():
    found = [line for key, lines in _hits().items() if key not in STILL_CARRYING for line in lines]

    assert found == []


def test_every_exempted_file_still_carries_what_it_is_exempt_for():
    assert set(STILL_CARRYING) <= set(_hits()), "drop the exemption of a file that no longer carries it"


@pytest.mark.parametrize(
    ("line", "named"),
    [
        (f"run: cd {OLD_PACKAGE} && uv run --no-sync pytest", True),
        (f"COPY {OLD_PACKAGE}/pyproject.toml {OLD_PACKAGE}/pyproject.toml", True),
        (f"uv run --no-sync mypy -p {OLD_PACKAGE}", True),
        (f'members = ["backend", "{OLD_PACKAGE}"]', True),
        (f"uv tool install --editable ./{OLD_PACKAGE}", True),
        (f"from {OLD_PACKAGE}.commands import deploy", True),
        (f"uv sync --reinstall-package fastapi-boilerplate-{OLD_PACKAGE}", True),
        ("docker compose exec redis redis-cli ping", False),
        ("from fastro.cli import app", False),
        ("fastro is a CLI", False),
        ("the clipboard and a clinic", False),
    ],
)
def test_the_package_needle(line: str, named: bool):
    assert bool(NAMES_OLD_PACKAGE.search(line)) is named


@pytest.mark.parametrize(
    ("line", "named"),
    [
        (f"uv run {OLD_COMMAND} deploy generate prod", True),
        (f"{OLD_COMMAND} env validate", True),
        (f"the `{OLD_COMMAND}` command", True),
        (f"uv run {OLD_COMMAND} ...", True),
        (f'plugin-ready <tspan fill="#0d9488">{OLD_COMMAND}</tspan> CLI', True),
        (f"a plugin-aware {OLD_COMMAND} CLI", True),
        (f"{OLD_COMMAND}-and-fastro", False),
        ("fastro make deploy prod", False),
    ],
)
def test_the_command_needle(line: str, named: bool):
    assert bool(NAMES_OLD_COMMAND.search(line)) is named


def _old_and_new_commands() -> list[tuple[str, str]]:
    """The pairs the changelog's entry for the package's removal gives, old command first."""
    changelog = (REPO_ROOT / "docs" / "changelog.md").read_text()
    unreleased = changelog.split("\n## Unreleased\n", 1)[1].split("\n## ", 1)[0]
    removed = " ".join(unreleased.split("#### Removed", 1)[1].split("\n#### ", 1)[0].split())

    return re.findall(rf"`{OLD_COMMAND} ([^`]+)` is `fastro ([^`]+)`", removed)


def test_fastro_still_answers_to_the_old_commands_the_changelog_maps():
    scripts = {point.name: point.value for point in importlib.metadata.entry_points(group="console_scripts")}
    pairs = _old_and_new_commands()

    assert scripts[OLD_COMMAND] == f"fastro.compat:{OLD_COMMAND}_main"
    assert len(pairs) == 3, pairs
    for old, new in pairs:
        assert compat.translate(old.split()) == new.split(), (old, new)
