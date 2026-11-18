"""Settings read the environment and the environment file when they're built, not when imported."""

from pathlib import Path

import pytest
from pydantic import ValidationError
from pydantic_settings import BaseSettings

import src.infrastructure.config.base as base
import src.infrastructure.config.settings as facade
from src.infrastructure.config.base import CoreSettings, EnvironmentOption, SecuritySettings
from src.infrastructure.config.settings import Settings


def test_a_variable_deleted_after_import_falls_back_to_the_default(reloaded, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("SECRET_KEY", raising=False)
    default = base.SecuritySettings().SECRET_KEY
    monkeypatch.setenv("SECRET_KEY", "set-before-the-import-" + "x" * 32)
    reloaded()

    monkeypatch.delenv("SECRET_KEY")

    assert base.SecuritySettings().SECRET_KEY == default


def test_the_file_found_is_read_when_the_settings_are_built(reloaded, found_file: Path, monkeypatch: pytest.MonkeyPatch):
    found = found_file
    monkeypatch.delenv("PYTEST_VERSION", raising=False)
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.delenv("APP_NAME", raising=False)
    reloaded()

    found.write_text("APP_NAME=Written After The Import\n")

    assert base.AppSettings().APP_NAME == "Written After The Import"


def test_no_file_is_read_under_pytest(reloaded, found_file: Path, monkeypatch: pytest.MonkeyPatch):
    found = found_file
    found.write_text("APP_NAME=Only The File Says So\n")
    monkeypatch.setenv("PYTEST_VERSION", "set")
    monkeypatch.delenv("APP_NAME", raising=False)
    reloaded()

    assert base.EnvSettings.model_config["env_file"] is None
    assert base.AppSettings().APP_NAME != "Only The File Says So"


def test_the_file_is_read_literally_as_it_always_was(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """A secret with `${...}` in it stays as written; a `#` is part of the value; `export` lines and
    names in another case aren't the setting."""
    for name in ("SECRET_KEY", "APP_NAME", "APP_DESCRIPTION"):
        monkeypatch.delenv(name, raising=False)
    stored = tmp_path / ".env"
    stored.write_text(
        "SECRET_KEY=ab${HOME}cd-long-enough-to-be-a-key-0123456789\n"
        "APP_NAME=foo # not a comment\n"
        "export APP_DESCRIPTION=exported\n"
        "app_description=lower\n"
    )
    built = Settings(_env_file=stored)

    assert built.SECRET_KEY == "ab${HOME}cd-long-enough-to-be-a-key-0123456789"
    assert built.APP_NAME == "foo # not a comment"
    assert built.APP_DESCRIPTION == Settings.model_fields["APP_DESCRIPTION"].default


def test_the_environment_wins_over_the_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    stored = tmp_path / ".env"
    stored.write_text("APP_NAME=From The File\n")
    monkeypatch.setenv("APP_NAME", "From The Environment")

    assert Settings(_env_file=stored).APP_NAME == "From The Environment"


def test_a_partial_class_ignores_the_names_other_classes_read(tmp_path: Path):
    stored = tmp_path / ".env"
    stored.write_text("POSTGRES_USER=elsewhere\n")

    SecuritySettings(_env_file=stored)


def test_a_misspelt_name_handed_to_the_constructor_is_refused():
    with pytest.raises(ValidationError):
        Settings(SECRET_KEYY="x")


def test_a_bad_environment_is_reported_without_the_other_settings(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ENVIRONMENT", "prod")
    monkeypatch.setenv("SECRET_KEY", "a-secret-nobody-should-see-0123456789abcdef")

    with pytest.raises(ValidationError) as refused:
        CoreSettings()

    assert [error["loc"] for error in refused.value.errors()] == [("ENVIRONMENT",)]
    assert "a-secret-nobody-should-see" not in str(refused.value)
    assert "a-secret-nobody-should-see" not in str(refused.value.errors())


@pytest.mark.parametrize(
    ("environment", "creates"),
    [(EnvironmentOption.LOCAL, True), (EnvironmentOption.DEVELOPMENT, True), (EnvironmentOption.PRODUCTION, False)],
)
def test_tables_are_created_on_startup_by_default_where_the_environment_builds_them(
    environment: EnvironmentOption, creates: bool, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.delenv("CREATE_TABLES_ON_STARTUP", raising=False)
    monkeypatch.setenv("ENVIRONMENT", environment.value)

    assert Settings().CREATE_TABLES_ON_STARTUP is creates


def test_tables_follow_the_environment_the_settings_are_built_with(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("CREATE_TABLES_ON_STARTUP", raising=False)
    monkeypatch.setenv("ENVIRONMENT", "local")

    assert Settings(ENVIRONMENT=EnvironmentOption.PRODUCTION).CREATE_TABLES_ON_STARTUP is False


def test_settings_constructed_without_validation_still_follow_the_process_environment(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ENVIRONMENT", "production")

    assert Settings.model_construct().CREATE_TABLES_ON_STARTUP is False


@pytest.mark.parametrize(("written", "read"), [("true", True), ("TRUE", True), ("1", True), ("false", False), ("0", False)])
def test_a_flag_reads_the_spellings_it_always_did(written: str, read: bool, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SECURITY_HEADERS_ENABLED", written)

    assert SecuritySettings().SECURITY_HEADERS_ENABLED is read


@pytest.mark.parametrize("written", ["yes", "on", "off", "t", ""])
def test_a_flag_refuses_a_spelling_it_never_read(written: str, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SECURITY_HEADERS_ENABLED", written)

    with pytest.raises(ValidationError):
        SecuritySettings()


@pytest.mark.parametrize(("written", "read"), [("30", 30), (" 30", 30), ("1_000", 1000), ("+5", 5)])
def test_a_number_reads_what_int_reads(written: str, read: int, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("POSTGRES_POOL_SIZE", written)

    assert CoreSettings().POSTGRES_POOL_SIZE == read


@pytest.mark.parametrize("written", ["1.0", "30.5", "thirty"])
def test_a_number_refuses_what_int_refuses(written: str, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("POSTGRES_POOL_SIZE", written)

    with pytest.raises(ValidationError):
        CoreSettings()


def test_a_flag_in_the_file_is_held_to_the_same_spellings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.delenv("SECURITY_HEADERS_ENABLED", raising=False)
    stored = tmp_path / ".env"
    stored.write_text("SECURITY_HEADERS_ENABLED=yes\n")

    with pytest.raises(ValidationError):
        SecuritySettings(_env_file=stored)


def test_a_class_written_the_old_way_still_composes_and_reads_its_variable(monkeypatch: pytest.MonkeyPatch):
    """`config` stays exported, so a project's own class written with it keeps working."""

    class OldStyle(BaseSettings):
        OLD_STYLE_VALUE: str = facade.config("OLD_STYLE_VALUE", default="declared")

    class Composed(OldStyle, Settings):
        pass

    monkeypatch.setenv("OLD_STYLE_VALUE", "from the environment")

    assert Composed().OLD_STYLE_VALUE == "from the environment"


class _Probe(base.EnvSettings):
    PROBE_LIMIT: int | None = None
    PROBE_FLAG: bool | None = None
    PROBE_IDS: list[int] = []


@pytest.mark.parametrize("written", ["1.0", ""])
def test_an_optional_number_refuses_what_int_refuses(written: str, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("PROBE_LIMIT", written)

    with pytest.raises(ValidationError):
        _Probe()


def test_an_optional_flag_is_held_to_the_same_spellings(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("PROBE_FLAG", "yes")

    with pytest.raises(ValidationError):
        _Probe()


def test_a_list_of_numbers_is_left_to_pydantic():
    with pytest.raises(ValidationError) as refused:
        _Probe(PROBE_IDS="[1, 2]")

    assert [error["type"] for error in refused.value.errors()] == ["list_type"]


def test_a_string_handed_to_the_constructor_is_held_to_the_same_rule():
    with pytest.raises(ValidationError):
        SecuritySettings(SECURITY_HEADERS_ENABLED="yes")
