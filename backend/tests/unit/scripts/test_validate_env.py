"""What the environment audit reports, and what it exits with.

The audit answers one question: what would production refuse about this configuration?
It therefore reads the settings as production whatever ``ENVIRONMENT`` says, so that a
development or staging configuration is held to the same gate, and so that a finding that
names an environment names the one it was checked for.
"""

import os
import secrets
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from pydantic import AliasChoices

from scripts.validate_env import audit, main
from src.infrastructure.config.settings import EnvironmentOption, Settings

BACKEND = Path(__file__).resolve().parents[3]

PRODUCTION_SHAPED: dict[str, Any] = {
    "ENVIRONMENT": EnvironmentOption.PRODUCTION,
    "CREATE_TABLES_ON_STARTUP": False,
    "EMAIL_BACKEND": "smtp",
    "EMAIL_SMTP_HOST": "smtp.example.com",
    "FRONTEND_URL": "https://app.example.com",
}
"""The settings whose defaults describe development rather than the production these stand for."""


def _settings(**overrides: Any) -> Settings:
    return Settings(**(PRODUCTION_SHAPED | overrides))


def _audited(monkeypatch, settings: Settings) -> None:
    """Answer the script with these settings instead of the ones the environment holds."""
    monkeypatch.setattr("scripts.validate_env.get_settings", lambda: settings)


def _accepted_names() -> set[str]:
    """Every name this project's settings take, a field's alias choices included.

    `SESSION_REDIS_PASSWORD` accepts `CACHE_REDIS_PASSWORD` as well, so a project with accounts
    and no cache still takes that name and reads the session password from it.
    """
    accepted = set()
    for name, field in Settings.model_fields.items():
        accepted.add(name)
        alias = field.validation_alias
        if isinstance(alias, str):
            accepted.add(alias)
        elif isinstance(alias, AliasChoices):
            accepted.update(choice for choice in alias.choices if isinstance(choice, str))

    return accepted


def _strong() -> dict[str, Any]:
    """A configuration production would accept, less whatever this project has no feature for.

    `Settings` forbids an input no field of its own takes, so a project without the cache, the
    limiter or the admin panel refuses their settings rather than ignoring them.
    """
    strong = {
        "SECRET_KEY": secrets.token_hex(32),
        "POSTGRES_PASSWORD": "a-strong-database-password",
        "CORS_ORIGINS": "https://app.example.com",
        "ADMIN_ENABLED": False,
        "DEBUG": False,
        "OPENAPI_URL": "",
        "CACHE_REDIS_PASSWORD": "redis-password",
        "RATE_LIMITER_REDIS_PASSWORD": "redis-password",
        "SESSION_SECURE_COOKIES": True,
        "SESSION_BACKEND": "redis",
        "RATE_LIMITER_BACKEND": "redis",
    }

    return {name: value for name, value in strong.items() if name in _accepted_names()}


def test_a_clean_configuration_says_so(monkeypatch, capsys):
    _audited(monkeypatch, _settings(**_strong()))

    code = main()

    assert code == 0
    assert "No issues found" in capsys.readouterr().out


def test_a_weak_configuration_is_refused_and_named(monkeypatch, capsys):
    """Settings the validator really refuses come out as critical findings that name them."""
    _audited(monkeypatch, _settings(SECRET_KEY="insecure-secret-key-change-this", POSTGRES_PASSWORD="postgres"))

    code = main()

    printed = capsys.readouterr().out
    assert code == 1
    assert "SECRET_KEY" in printed
    assert "Database is using default credentials" in printed


def test_warnings_are_reported_even_when_something_is_critical(monkeypatch, capsys):
    """The warnings used to be computed only when nothing critical was found.

    Both findings are core: the placeholder key is critical and debug mode is a warning, so a
    project with no features selected still produces one of each.
    """
    _audited(monkeypatch, _settings(SECRET_KEY="insecure-secret-key-change-this", DEBUG=True))

    code = main()

    printed = capsys.readouterr().out
    assert code == 1
    assert "Critical (" in printed
    assert "Warnings (" in printed


def test_warnings_alone_do_not_fail_the_audit(monkeypatch, capsys):
    """A warning is something to look at, not something that would stop a boot.

    Debug mode rather than an unprotected cache: the cache is a feature, and this test runs in
    projects that didn't select it.
    """
    _audited(monkeypatch, _settings(**(_strong() | {"DEBUG": True})))

    code = main()

    printed = capsys.readouterr().out
    assert code == 0
    assert "Warnings (" in printed
    assert "Critical (" not in printed


def test_every_finding_names_the_environment_it_is_checked_for(monkeypatch, capsys):
    """Audited as production, a finding that names a development environment is a lie.

    The table-creation finding is the one asked for, because it is core: the email backend names
    the environment too, but only a project with accounts has anything to email.
    """
    _audited(monkeypatch, _settings(ENVIRONMENT=EnvironmentOption.DEVELOPMENT, CREATE_TABLES_ON_STARTUP=True))

    main()

    printed = capsys.readouterr().out
    assert "in production" in printed
    assert "in development" not in printed


def test_the_audited_settings_carry_the_environment_as_the_app_reads_it(monkeypatch):
    """The app factory and the logger read ``ENVIRONMENT.value``, which a plain string has not."""
    handed: list[Settings] = []
    _audited(monkeypatch, _settings(ENVIRONMENT=EnvironmentOption.DEVELOPMENT))

    class _Validator:
        def __init__(self, settings: Settings):
            handed.append(settings)

        def audit(self) -> tuple[list[str], list[str]]:
            return [], []

    monkeypatch.setattr("scripts.validate_env.ProductionSecurityValidator", _Validator)
    audit()

    assert handed[0].ENVIRONMENT.value == "production"


def _run(environment: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "scripts.validate_env"],
        cwd=BACKEND,
        env={
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": os.environ.get("HOME", "/tmp"),
            "PYTEST_VERSION": os.environ.get("PYTEST_VERSION", "1"),
            **environment,
        },
        capture_output=True,
        text=True,
        timeout=120,
    )


@pytest.mark.parametrize(("key", "code"), [("placeholder", 1), ("drawn", 0)])
def test_it_runs_as_a_module_and_exits_on_what_it_found(key: str, code: int):
    """``python -m scripts.validate_env`` is what the blueprint declares as a command.

    The key is drawn here rather than in the parameter list, where it would land in the
    test's id: ``pytest -n auto`` refuses a run whose workers collected different ids.
    """
    secret = secrets.token_hex(32) if key == "drawn" else "insecure-secret-key-change-this"
    environment = {
        "PYTHONPATH": str(BACKEND),
        "ENVIRONMENT": "development",
        "SECRET_KEY": secret,
        "POSTGRES_PASSWORD": "a-strong-database-password",
        "CORS_ORIGINS": "https://app.example.com",
        "ADMIN_ENABLED": "false",
        "DEBUG": "false",
        "OPENAPI_URL": "",
        "CACHE_REDIS_PASSWORD": "redis-password",
        "RATE_LIMITER_REDIS_PASSWORD": "redis-password",
        "SESSION_SECURE_COOKIES": "true",
        "CREATE_TABLES_ON_STARTUP": "false",
        "EMAIL_BACKEND": "smtp",
        "EMAIL_SMTP_HOST": "smtp.example.com",
        "FRONTEND_URL": "https://app.example.com",
        "SESSION_BACKEND": "redis",
        "RATE_LIMITER_BACKEND": "redis",
    }

    result = _run(environment)

    assert result.returncode == code, result.stdout + result.stderr
