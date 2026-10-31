"""The key the script prints, and why it sometimes draws more than once.

``SECRET_KEY`` is refused at startup in production when the project's own rules read it as
something a person typed. A generator that printed such a key would send you into that
refusal, so it draws again while the rules refuse what it drew.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.gen_secret import generate
from src.infrastructure.config.settings import EnvironmentOption, Settings
from src.infrastructure.security.production_validator import ProductionSecurityValidator
from src.infrastructure.security.secret_key import is_weak_secret_key

BACKEND = Path(__file__).resolve().parents[3]

REFUSED = "e48102bfe6ac2eac3aa8623456789a6030e4fa7dee3cd173bfb7941f2f819678"
"""A hex key the rules refuse: it runs through eight consecutive digits."""


def _run(*arguments: str) -> subprocess.CompletedProcess[str]:
    """Run the script from ``backend/``, with nothing configured but the interpreter."""
    environment = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": os.environ.get("HOME", "/tmp"),
        "PYTHONPATH": str(BACKEND),
    }

    return subprocess.run(
        [sys.executable, *arguments],
        cwd=BACKEND,
        env=environment,
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_the_key_it_prints_is_one_the_validator_accepts():
    """The script is what an operator runs to satisfy the validator, so ask the validator."""
    key = generate()

    validator = ProductionSecurityValidator(Settings(SECRET_KEY=key, ENVIRONMENT=EnvironmentOption.PRODUCTION))

    assert len(key) == 64
    assert not validator._is_insecure_secret_key()


def test_a_key_the_rules_refuse_is_drawn_again(monkeypatch):
    """One hex key in twelve million runs through eight digits, which production refuses."""
    accepted = "7b1c9d4e2a6f8305b4c7e1d9f2a6b8c30d5e7f91a2b3c4d5e6f708192a3b4c5d"
    draws = iter([REFUSED, accepted])
    monkeypatch.setattr("scripts.gen_secret.secrets.token_hex", lambda size: next(draws))

    assert is_weak_secret_key(REFUSED)
    assert generate() == accepted


def test_it_gives_up_after_the_draws_it_allows(monkeypatch):
    """Drawing for ever would hang; the last draw is printed whatever the rules say."""
    monkeypatch.setattr("scripts.gen_secret.secrets.token_hex", lambda size: REFUSED)

    assert generate() == REFUSED


def test_the_byte_count_decides_the_length():
    assert len(generate(16)) == 32


@pytest.mark.parametrize("invocation", [("scripts/gen_secret.py",), ("-m", "scripts.gen_secret")])
def test_it_runs_the_way_the_documentation_runs_it(invocation: tuple[str, ...]):
    """As a file from ``backend/``, and as a module, which is what the blueprint declares."""
    result = _run(*invocation)

    assert result.returncode == 0, result.stderr
    assert len(result.stdout.strip()) == 64


@pytest.mark.parametrize("count", ["8", "256", "many"])
def test_a_byte_count_the_script_will_not_take_is_refused(count: str):
    """A short key is one the rules would refuse anyway, and a usage error exits 2."""
    result = _run("scripts/gen_secret.py", "--bytes", count)

    assert result.returncode == 2
    assert result.stdout.strip() == ""


def test_it_prints_the_key_and_nothing_else():
    """The documented use pipes it (``| gh secret set SECRET_KEY``), so a log line would go too.

    Importing ``src.infrastructure.security`` configures logging, which writes to stdout.
    """
    result = _run("-m", "scripts.gen_secret")

    assert result.stdout.count("\n") == 1
    assert len(result.stdout.strip()) == 64
