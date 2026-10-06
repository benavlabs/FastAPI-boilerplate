"""``bp env``: what it reports about a configuration, and what it refuses."""

import secrets
import warnings
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

import cli.app
from cli import plugins
from cli.commands import env

runner = CliRunner()


def _backend_settings(**overrides):
    """The app's own settings object, as the command builds it.

    ``CREATE_TABLES_ON_STARTUP`` and ``EMAIL_BACKEND`` are passed in because their defaults
    describe a development environment, not the production one these settings stand for.
    """
    module = env._app_module("src.infrastructure.config.settings")

    return module.Settings(ENVIRONMENT="production", CREATE_TABLES_ON_STARTUP=False, EMAIL_BACKEND="smtp", **overrides)


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
    """The command is what operators run to satisfy the validator, so ask the validator."""
    result = runner.invoke(env.app, ["gen-secret"])
    key = result.output.strip()

    settings = _backend_settings(SECRET_KEY=key)
    validator_module = env._app_module("src.infrastructure.security.production_validator")

    assert result.exit_code == 0
    assert len(key) == 64
    assert not validator_module.ProductionSecurityValidator(settings)._is_insecure_secret_key()


REFUSED_BY_THE_APP = "e48102bfe6ac2eac3aa8623456789a6030e4fa7dee3cd173bfb7941f2f819678"


def test_a_key_the_app_would_refuse_is_drawn_again(monkeypatch):
    """One hex key in twelve million runs through eight digits, which production refuses."""
    accepted = secrets.token_hex(32)
    draws = iter([REFUSED_BY_THE_APP, accepted])
    monkeypatch.setattr(env.secrets, "token_hex", lambda size: next(draws))

    result = runner.invoke(env.app, ["gen-secret"])

    assert result.exit_code == 0
    assert result.output.strip() == accepted


def test_the_first_draw_is_printed_outside_a_project(monkeypatch, tmp_path):
    """Nothing to ask: the rules live in the project, and the command still answers."""
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(env.app, ["gen-secret"])

    assert result.exit_code == 0
    assert len(result.output.strip()) == 64


def test_a_plugin_warning_is_written_to_stderr(capsys):
    """On stdout it would corrupt whatever the caller is piping command output into."""
    plugins.emit_plugin_warnings_to_stderr()

    warnings.showwarning("entry point 'acme' failed to load", RuntimeWarning, "plugins.py", 1)
    captured = capsys.readouterr()

    assert "acme" in captured.err
    assert captured.out == ""


def test_mounting_the_plugins_routes_their_warnings(monkeypatch):
    routed: list[bool] = []
    monkeypatch.setattr(plugins, "emit_plugin_warnings_to_stderr", lambda: routed.append(True))

    cli.app._mount_command_plugins()

    assert routed == [True]


@pytest.fixture
def real_validator(monkeypatch):
    """The command with the app's own validator, against settings the test picks."""
    validator_module = env._app_module("src.infrastructure.security.production_validator")

    def with_settings(**overrides):
        settings = _backend_settings(**overrides)
        monkeypatch.setattr(
            env,
            "_app_module",
            lambda name: validator_module if "production_validator" in name else SimpleNamespace(get_settings=lambda: settings),
        )

    return with_settings


def test_validate_runs_the_real_validator_against_a_weak_configuration(real_validator):
    """The stubs above pin the report's shape; this pins that the command really audits."""
    real_validator(SECRET_KEY="insecure-secret-key-change-this", POSTGRES_PASSWORD="postgres")

    result = runner.invoke(env.app, ["validate"])

    assert result.exit_code == 1
    assert "SECRET_KEY" in result.output
    assert "Database is using default credentials" in result.output


def test_validate_reports_a_strong_configuration_as_clean(real_validator):
    """The real validator, with nothing to complain about."""
    real_validator(
        SECRET_KEY=secrets.token_hex(32),
        POSTGRES_PASSWORD="a-strong-database-password",
        CORS_ORIGINS="https://app.example.com",
        ADMIN_ENABLED=False,
        DEBUG=False,
        OPENAPI_URL="",
        CACHE_REDIS_PASSWORD="redis-password",
        RATE_LIMITER_REDIS_PASSWORD="redis-password",
        SESSION_SECURE_COOKIES=True,
    )

    result = runner.invoke(env.app, ["validate"])

    assert result.exit_code == 0, result.output
