"""Tests for lazy engine creation."""

import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy.pool import NullPool

from src.infrastructure.database import session as session_module
from src.infrastructure.database.session import build_engine, get_engine

BACKEND_DIR = Path(__file__).parents[4]


@pytest.fixture
def no_engine():
    """Run with a clean module state and restore whatever was there before."""
    previous_engine = session_module._engine
    previous_factory = session_module._session_factory
    session_module._engine = None
    session_module._session_factory = None

    yield

    session_module._engine = previous_engine
    session_module._session_factory = previous_factory


class TestBuildEngine:
    """Test cases for build_engine."""

    def test_applies_pool_defaults_from_settings(self):
        """The default engine is pooled according to the Postgres settings."""
        with patch("src.infrastructure.database.session.create_async_engine") as create:
            build_engine()

        kwargs = create.call_args.kwargs
        assert "pool_size" in kwargs
        assert "max_overflow" in kwargs
        assert "pool_pre_ping" in kwargs
        assert "pool_recycle" in kwargs

    def test_omits_queue_pool_sizing_for_a_custom_pool(self):
        """Pools that do not queue connections reject the sizing arguments."""
        with patch("src.infrastructure.database.session.create_async_engine") as create:
            build_engine(poolclass=NullPool)

        kwargs = create.call_args.kwargs
        assert kwargs["poolclass"] is NullPool
        assert "pool_size" not in kwargs
        assert "max_overflow" not in kwargs

    def test_overrides_win_over_defaults(self):
        """Callers can replace any default."""
        with patch("src.infrastructure.database.session.create_async_engine") as create:
            build_engine(echo=True)

        assert create.call_args.kwargs["echo"] is True


class TestGetEngine:
    """Test cases for get_engine."""

    def test_creates_the_engine_on_first_call(self, no_engine):
        """Nothing exists until someone asks for it."""
        with patch.object(session_module, "build_engine") as build:
            assert session_module._engine is None

            get_engine()

            build.assert_called_once()

    def test_reuses_the_same_engine(self, no_engine):
        """Later calls hand back the cached engine."""
        with patch.object(session_module, "build_engine") as build:
            first = get_engine()
            second = get_engine()

        assert first is second
        assert build.call_count == 1

    def test_importing_the_module_creates_no_engine(self):
        """Importing must not open a connection pool."""
        env = {**os.environ, "PYTHONPATH": str(BACKEND_DIR)}
        code = (
            "import src.infrastructure.database.session as s; "
            "assert s._engine is None; "
            "assert s._session_factory is None; "
            "print('no engine on import')"
        )

        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=BACKEND_DIR,
            env=env,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, result.stderr
        assert "no engine on import" in result.stdout


class TestLegacyEngineAttribute:
    """The module-level ``engine`` name is kept for backward compatibility."""

    def test_resolves_to_the_shared_engine(self, no_engine):
        """``session.engine`` is the engine ``get_engine()`` hands out."""
        sentinel = object()
        session_module._engine = sentinel

        assert session_module.engine is sentinel

    def test_unknown_attributes_still_raise(self):
        """The shim only covers ``engine``."""
        with pytest.raises(AttributeError):
            session_module.not_a_real_attribute
