"""Which environment file the settings read, and what happens when there is none.

A container is configured through the environment rather than a file, so the import has
to be quiet about the file it did not find: anything it prints lands in front of every
operator command the image runs.
"""

import importlib
import logging
import os
import warnings

import pytest

import src.infrastructure.config.base as base


@pytest.fixture
def reloaded():
    """Re-import the module under the test's conditions, and put it back afterwards."""
    yield lambda: importlib.reload(base)
    importlib.reload(base)


def test_with_no_environment_file_nothing_warns(reloaded, monkeypatch, caplog):
    """Starlette warns about a file it was handed and could not find, so it is handed none."""
    monkeypatch.setattr(os.path, "isfile", lambda path: False)
    monkeypatch.delenv("PYTEST_VERSION", raising=False)
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)

    with warnings.catch_warnings(record=True) as raised, caplog.at_level(logging.INFO):
        warnings.simplefilter("always")
        reloaded()

    assert [str(warning.message) for warning in raised] == []
    assert base.env_path is None
    assert "settings are read from the environment" in caplog.text


def test_an_environment_file_that_exists_is_the_one_read(reloaded, monkeypatch, tmp_path, caplog):
    stored = tmp_path / ".env"
    stored.write_text("ENVIRONMENT=local\n")
    monkeypatch.setattr(base.os.path, "realpath", lambda path: str(tmp_path / "src" / "infrastructure" / "config" / "base.py"))
    monkeypatch.delenv("PYTEST_VERSION", raising=False)
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)

    with caplog.at_level(logging.INFO):
        reloaded()

    assert base.env_path == str(stored)
    assert f"Using environment file at: {stored}" in caplog.text
