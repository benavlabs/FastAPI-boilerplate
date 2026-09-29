"""``bp env``: what it reports about a configuration, and what it refuses."""

from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from cli.commands import env

runner = CliRunner()


@pytest.fixture
def audited(monkeypatch):
    """Answer the command with a validator whose audit we control."""

    def audit_returning(errors: list[str], warnings: list[str]):
        class _Validator:
            def __init__(self, settings):
                self.settings = settings

            def audit(self):
                return errors, warnings

            def _is_production(self):
                return True

        module = SimpleNamespace(ProductionSecurityValidator=_Validator)
        monkeypatch.setattr(
            env,
            "_app_module",
            lambda name: module if "production_validator" in name else SimpleNamespace(get_settings=lambda: object()),
        )

    return audit_returning


def test_warnings_are_reported_even_when_something_is_critical(audited):
    """The warnings used to be computed only when nothing critical was found."""
    audited(["SECRET_KEY is using a default value"], ["Redis has no password"])

    result = runner.invoke(env.app, ["validate"])

    assert result.exit_code == 1
    assert "SECRET_KEY" in result.output
    assert "Redis has no password" in result.output


def test_warnings_alone_do_not_fail_the_command(audited):
    audited([], ["Redis has no password"])

    result = runner.invoke(env.app, ["validate"])

    assert result.exit_code == 0
    assert "Redis has no password" in result.output


def test_a_clean_configuration_says_so(audited):
    audited([], [])

    result = runner.invoke(env.app, ["validate"])

    assert result.exit_code == 0
    assert "No issues found" in result.output


def test_gen_secret_produces_a_key_the_validator_accepts():
    """The command is what operators run to satisfy the validator, so it has to."""
    result = runner.invoke(env.app, ["gen-secret"])

    key = result.output.strip()

    assert result.exit_code == 0
    assert len(key) == 64
    assert int(key, 16) >= 0
