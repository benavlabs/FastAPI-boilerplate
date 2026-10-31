"""What the baseline writes, what it refuses, and what it leaves behind.

The container and alembic are mocked, so the suite needs no Docker: what is checked here is
the script's own reasoning. The revision it writes has to be the baseline rather than any
revision, and ``--check`` has to leave ``migrations/versions/`` exactly as it found it, since
that is the mode `fastro verify` runs in a project it has just generated.
"""

import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from scripts import baseline
from src.infrastructure.database.session import Base

HOST = "127.0.0.1"
PORT = 54321

BACKEND = Path(baseline.__file__).resolve().parents[1]


class _Container:
    """The pieces of a ``PostgresContainer`` the script reads."""

    username = "baseline-user"
    password = "baseline-password"
    dbname = "baseline-db"

    def __init__(self, image: str):
        self.image = image

    def __enter__(self) -> "_Container":
        return self

    def __exit__(self, *exception: Any) -> None:
        return None

    def get_container_host_ip(self) -> str:
        return HOST

    def get_exposed_port(self, port: int) -> int:
        return PORT


class _Alembic:
    """Alembic as the script calls it: a recorder that writes the revision autogenerate would."""

    def __init__(self, versions: Path, *, revision: str = "0a1b2c3d4e5f", slug: str | None = None, failing: str | None = None):
        self.versions = versions
        self.revision = revision
        self.slug = slug
        self.failing = failing
        self.calls: list[tuple[str, ...]] = []
        self.environments: list[dict[str, str]] = []

    def __call__(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        self.calls.append(arguments)
        self.environments.append(dict(os.environ))
        if self.failing == arguments[0]:
            return subprocess.CompletedProcess(list(arguments), 1, "", f"{arguments[0]} went wrong")

        if arguments[0] == "revision":
            slug = self.slug or arguments[arguments.index("-m") + 1]
            (self.versions / f"{self.revision}_{slug}.py").write_text(f'revision = "{self.revision}"\n')

        return subprocess.CompletedProcess(list(arguments), 0, "", "")


@pytest.fixture
def versions(tmp_path: Path, monkeypatch) -> Path:
    directory = tmp_path / "versions"
    directory.mkdir()
    monkeypatch.setattr(baseline, "VERSIONS", directory)

    return directory


@pytest.fixture(autouse=True)
def _restored_environment() -> Iterator[None]:
    """The script writes the container's details into the environment, as alembic reads them."""
    before = dict(os.environ)

    yield

    os.environ.clear()
    os.environ.update(before)


@pytest.fixture
def container(monkeypatch) -> None:
    monkeypatch.setattr(baseline, "PostgresContainer", _Container)


@pytest.fixture
def alembic(versions, monkeypatch) -> _Alembic:
    """Alembic itself is never run: what it would do to the tree is what the script reasons about."""
    recorder = _Alembic(versions)
    monkeypatch.setattr(baseline, "alembic", recorder)

    return recorder


def _schema_of(declared: dict[str, list[str]]):
    async def read(url: str) -> dict[str, list[str]]:
        return declared

    return read


@pytest.fixture
def matching(monkeypatch) -> None:
    """A database the baseline left holding exactly what the models declare."""
    monkeypatch.setattr(baseline, "created_schema", _schema_of(baseline.declared_schema()))


def _written(versions: Path) -> dict[str, str]:
    return {path.name: path.read_text() for path in versions.glob("*.py")}


def test_it_writes_one_revision_named_after_the_baseline(versions, container, matching, alembic, capsys):
    code = baseline.main([])

    assert code == 0, capsys.readouterr()
    assert list(_written(versions)) == ["0a1b2c3d4e5f_baseline.py"]
    assert "tables" in capsys.readouterr().out


def test_it_autogenerates_the_baseline_and_applies_it(versions, container, matching, alembic):
    baseline.main([])

    assert alembic.calls == [("revision", "--autogenerate", "-m", "baseline"), ("upgrade", "head")]


def test_check_leaves_the_versions_directory_as_it_found_it(versions, container, matching, alembic):
    before = _written(versions)

    code = baseline.main(["--check"])

    assert code == 0
    assert _written(versions) == before
    assert ("revision", "--autogenerate", "-m", "baseline") in alembic.calls


def test_the_commands_run_against_the_container(versions, container, matching, alembic):
    baseline.main([])

    environment = alembic.environments[0]
    assert environment["POSTGRES_SERVER"] == HOST
    assert environment["POSTGRES_PORT"] == str(PORT)
    assert environment["POSTGRES_USER"] == _Container.username
    assert environment["POSTGRES_PASSWORD"] == _Container.password
    assert environment["POSTGRES_DB"] == _Container.dbname
    assert environment["DATABASE_URL"] == "", "a configured URL wins over these, and names the real database"


def test_a_database_the_models_do_not_declare_is_refused(versions, container, alembic, monkeypatch, capsys):
    """The table named here is one no project declares, so it is a mismatch whatever is selected."""
    monkeypatch.setattr(baseline, "created_schema", _schema_of({"alembic_version": [], "nothing_declares_this": []}))

    code = baseline.main(["--check"])

    printed = capsys.readouterr()
    assert code == 1
    assert "while the models declare" in printed.err
    assert _written(versions) == {}


def test_a_failed_autogenerate_is_reported_with_what_alembic_printed(versions, container, matching, monkeypatch, capsys):
    monkeypatch.setattr(baseline, "alembic", _Alembic(versions, failing="revision"))

    code = baseline.main([])

    printed = capsys.readouterr()
    assert code == 1
    assert "revision went wrong" in printed.err
    assert _written(versions) == {}


def test_a_failed_upgrade_is_withdrawn_under_check(versions, container, matching, monkeypatch, capsys):
    monkeypatch.setattr(baseline, "alembic", _Alembic(versions, failing="upgrade"))

    code = baseline.main(["--check"])

    printed = capsys.readouterr()
    assert code == 1
    assert "upgrade went wrong" in printed.err
    assert _written(versions) == {}


def test_a_revision_that_is_not_the_baseline_is_refused(versions, container, matching, monkeypatch, capsys):
    """Alembic names the file after its own slug, and a project's first revision is the baseline."""
    monkeypatch.setattr(baseline, "alembic", _Alembic(versions, slug="add_a_column"))

    code = baseline.main(["--check"])

    assert code == 1
    assert "is not the baseline" in capsys.readouterr().err


def test_a_project_that_already_has_a_history_is_refused(versions, container, matching, alembic, capsys):
    (versions / "f5e4d3c2b1a0_add_a_column.py").write_text('revision = "f5e4d3c2b1a0"\n')
    before = _written(versions)

    code = baseline.main([])

    printed = capsys.readouterr()
    assert code == 1
    assert "f5e4d3c2b1a0_add_a_column.py" in printed.err
    assert _written(versions) == before


def test_the_declared_schema_is_the_one_the_models_build(versions):
    """The tables are the ones this project's features declare, read rather than listed.

    A project without accounts has no `user`, and one with no features has only alembic's own,
    which the script adds because a baseline creates the table alembic records itself in.
    """
    declared = baseline.declared_schema()

    assert declared["alembic_version"] == []
    assert set(declared) == set(Base.metadata.tables) | {"alembic_version"}
    assert all(indexes == sorted(indexes) for indexes in declared.values())


_COLD_SCHEMA = """
from scripts.baseline import declared_schema

print(sorted(name for name in declared_schema() if name != "alembic_version"))
"""


def test_the_script_imports_the_models_itself():
    """Only a cold interpreter can tell: in the suite, `tests/conftest.py` has imported the app,
    which imports every model, so the metadata is already full whatever the script does.

    A project that declares no models of its own cannot tell an import that did nothing from one
    that worked, so it skips rather than passing for the wrong reason.
    """
    declared = sorted(Base.metadata.tables)
    if not declared:
        pytest.skip("this project declares no models, so a missing import looks like a working one")

    result = subprocess.run(
        [sys.executable, "-c", _COLD_SCHEMA],
        cwd=BACKEND,
        env={**os.environ, "PYTHONPATH": str(BACKEND)},
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip().splitlines()[-1] == str(declared), "the settings log to stdout before it prints"


def test_running_it_as_a_module_takes_the_check_flag():
    """``--check`` is what verify runs, so an argument parser that refuses it is a broken verify."""
    result = subprocess.run(
        [sys.executable, "-m", "scripts.baseline", "--help"],
        cwd=BACKEND,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(BACKEND)},
        timeout=120,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "--check" in result.stdout
