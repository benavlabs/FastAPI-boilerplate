"""Which environment file the settings read, and what happens when there is none.

A container is configured through the environment rather than a file, so the import has
to be quiet about the file it did not find: anything it prints lands in front of every
operator command the image runs.
"""

import logging
import os
import warnings

import src.infrastructure.config.base as base


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


def test_an_environment_file_that_exists_is_the_one_read(reloaded, found_file, monkeypatch, caplog):
    stored = found_file
    monkeypatch.delenv("PYTEST_VERSION", raising=False)
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)

    with caplog.at_level(logging.INFO):
        reloaded()

    assert base.env_path == str(stored)
    assert f"Using environment file at: {stored}" in caplog.text
