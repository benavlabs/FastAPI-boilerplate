"""The commands the README and the docs tell a reader to run are ones the pinned fastro has."""

import re
import shlex
from collections.abc import Iterator

import click
import pytest
import typer.main
from fastro.cli import app
from retired import OLD_COMMAND, RUNS_OLD_COMMAND, shown_pages

NOT_YET_SWITCHED = ("docs/cli/",)
"""Pages B3 item 2b deletes, with the old command in them until it does."""

FASTRO = typer.main.get_command(app)

LAUNCHERS = (("uv", "run", "--no-sync"), ("uv", "run"), ("uvx",), ("python", "-m"))

STOPS = {"|", "&&", "||", ";"}


def _pages() -> Iterator[tuple[str, str]]:
    for name, text in shown_pages():
        if not name.startswith(NOT_YET_SWITCHED):
            yield name, text


def _code(text: str) -> Iterator[tuple[str, bool]]:
    """Every line of every fenced block, a commented-out alternative included, and every inline
    code span outside them, each with whether it is a line a reader runs."""
    fenced = False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            fenced = not fenced
        elif fenced:
            yield re.sub(r"^\s*#\s*(?:or:\s*)?", "", line), True
        else:
            yield from ((span, False) for span in re.findall(r"`([^`\n]+)`", line))


def _fastro_words(code: str) -> list[str] | None:
    """The words after `fastro` when the code runs it, through any launcher; `None` when it doesn't."""
    lexer = shlex.shlex(code.strip().removeprefix("$ "), posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    try:
        words = list(lexer)
    except ValueError:
        return None
    for index, word in enumerate(words):
        if word in STOPS:
            words = words[:index]
            break
    for launcher in LAUNCHERS:
        if tuple(words[: len(launcher)]) == launcher:
            words = words[len(launcher) :]
            break
    if not words or words[0].split("@")[0] != "fastro":
        return None

    return words[1:]


def _commands() -> list[tuple[str, list[str], bool]]:
    return [
        (f"{name}: {code.strip()}", words, runs)
        for name, text in _pages()
        for code, runs in _code(text)
        if (words := _fastro_words(code)) is not None
    ]


def _refusal(words: list[str], runs: bool = True) -> str | None:
    """Why the pinned fastro would refuse these words, or `None` when it takes them.

    A command named in a sentence, with nothing after it, only has to exist; a line a reader
    runs has to parse."""
    command: click.Command = FASTRO
    remaining = list(words)
    while isinstance(command, click.Group) and remaining and not remaining[0].startswith("-"):
        if remaining[0] not in command.commands:
            return f"{command.name} has no command {remaining[0]!r}"
        command = command.commands[remaining.pop(0)]
    if isinstance(command, click.Group) and remaining:
        return f"{command.name} takes a command before {remaining[0]!r}"
    if not remaining and not runs:
        return None
    try:
        command.make_context(command.name, remaining)
    except click.ClickException as refused:
        return refused.format_message()

    return None


def test_no_page_a_reader_sees_runs_the_retired_command():
    """B3 item 2 removes the old developer CLI; every command it ran is a fastro command now."""
    found = [
        f"{name}:{number}"
        for name, text in _pages()
        for number, line in enumerate(text.splitlines(), 1)
        if RUNS_OLD_COMMAND.search(line)
    ]

    assert not found, found


def test_the_pages_show_fastro_commands():
    """The rule below has something to read, so a reader that stopped finding commands would show."""
    assert any(words[:2] == ["make", "deploy"] and runs for _, words, runs in _commands())


@pytest.mark.parametrize(("where", "words", "runs"), _commands(), ids=[where for where, _, _ in _commands()])
def test_every_fastro_command_a_page_shows_is_one_the_pinned_fastro_takes(where: str, words: list[str], runs: bool):
    assert _refusal(words, runs) is None, (where, _refusal(words, runs))


FENCE = "`" * 3


@pytest.mark.parametrize(
    ("page", "refused"),
    [
        (f"{FENCE}bash\nuv run --no-sync fastro make deploy prod --wokers 8\n{FENCE}", True),
        ("Run `fastro env gen-secret`.", True),
        ("Run `fastro make deploy prodd`.", True),
        ("Run `fastro env secret --bytes 8`.", True),
        ("Run `fastro make deploy prod --workers many`.", True),
        ("Run `fastro make deploy prod extra`.", True),
        (f"{FENCE}bash\n# or: uv run --no-sync fastro make deploy prodd\n{FENCE}", True),
        (f"{FENCE}bash\nuv run --no-sync fastro make deploy  # writes the compose file\n{FENCE}", True),
        ("`fastro make deploy` writes it.", False),
        ("Run `fastro make deploy --workers 8 prod`.", False),
        ("Run `fastro make deploy prod|cat`.", False),
        (f"{FENCE}bash\n# or: uv run --no-sync fastro make deploy prod\n{FENCE}", False),
        (f"{FENCE}bash\n$ uv run --no-sync fastro env secret --bytes 16 | gh secret set SECRET_KEY\n{FENCE}", False),
        ("Run `uv run --no-sync fastro make deploy nginx --internal-subnet=10.89.0.0/24 --dry-run`.", False),
        (f"{FENCE}bash\nfastro sync --check  # in the blueprint repo\n{FENCE}", False),
    ],
)
def test_the_reader_refuses_what_fastro_would(page: str, refused: bool):
    read = [(words, runs) for code, runs in _code(page) if (words := _fastro_words(code)) is not None]

    assert len(read) == 1, read
    assert (_refusal(*read[0]) is not None) is refused


@pytest.mark.parametrize(
    ("line", "runs"),
    [
        (f"uv run --no-sync {OLD_COMMAND} env validate", True),
        (f"the `{OLD_COMMAND}` tool", True),
        (f"{OLD_COMMAND}-and-fastro", False),
        ("redis-cli ping", False),
    ],
)
def test_the_old_command_is_read_where_it_runs(line: str, runs: bool):
    assert bool(RUNS_OLD_COMMAND.search(line)) is runs
