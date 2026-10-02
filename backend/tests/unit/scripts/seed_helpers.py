"""Running a seed script the way a user runs it: as a subprocess, from ``backend/``."""

import os
import subprocess
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlsplit

from src.infrastructure.database import session as session_module

BACKEND_DIR = Path(__file__).resolve().parents[3]


def script_environment(database_url: str, **extra: str) -> dict[str, str]:
    """The whole environment for a script run: the pieces of ``database_url``, plus ``extra``.

    Sets ``POSTGRES_SERVER``, ``POSTGRES_PORT``, ``POSTGRES_USER``,
    ``POSTGRES_PASSWORD`` and ``POSTGRES_DB`` from ``database_url``, a blank
    ``DATABASE_URL``, memory session and limiter backends, and the paths a
    subprocess needs. ``extra`` overrides any of them, and a script reads
    ``backend/.env`` for anything left out, which pytest itself does not.
    """
    parsed = urlsplit(database_url)

    return {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": os.environ.get("HOME", "/tmp"),
        "PYTHONPATH": str(BACKEND_DIR),
        "ENVIRONMENT": "local",
        "SECRET_KEY": "a-secret-key-only-this-test-uses",
        "SESSION_BACKEND": "memory",
        "RATE_LIMITER_BACKEND": "memory",
        "POSTGRES_SERVER": parsed.hostname or "localhost",
        "POSTGRES_PORT": str(parsed.port or 5432),
        "POSTGRES_USER": parsed.username or "test",
        "POSTGRES_PASSWORD": parsed.password or "test",
        "POSTGRES_DB": (parsed.path or "/test").lstrip("/"),
        "DATABASE_URL": "",
        **extra,
    }


def run_script(name: str, environment: dict[str, str]) -> subprocess.CompletedProcess[str]:
    """Run ``scripts/<name>.py`` from ``backend/``, as the documentation does."""
    return subprocess.run(
        [sys.executable, f"scripts/{name}.py"],
        cwd=BACKEND_DIR,
        env=environment,
        capture_output=True,
        text=True,
        timeout=120,
    )


@contextmanager
def no_cached_engine() -> Iterator[None]:
    """Run with an empty engine cache, restoring whatever was cached before."""
    previous_engine = session_module._engine
    previous_factory = session_module._session_factory
    session_module._engine = None
    session_module._session_factory = None

    try:
        yield
    finally:
        session_module._engine = previous_engine
        session_module._session_factory = previous_factory
