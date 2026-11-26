import importlib
from pathlib import Path

import pytest

import src.infrastructure.config.base as base


@pytest.fixture
def reloaded():
    """Re-import the settings module under the test's conditions, and put it back afterwards."""
    yield lambda: importlib.reload(base)
    importlib.reload(base)


@pytest.fixture
def found_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """``tmp_path/.env``, as the file the module finds where it would find ``backend/.env``."""
    found = tmp_path / ".env"
    found.write_text("")
    monkeypatch.setattr(base.os.path, "realpath", lambda path: str(tmp_path / "src" / "infrastructure" / "config" / "base.py"))

    return found
