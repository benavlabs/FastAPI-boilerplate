"""A route module of this feature has to import on its own.

Alembic, a worker or a script reaches the app that way, and ``require_permissions``
validates its names at import time, so discovery has to have run by then.
"""

import subprocess
import sys
from pathlib import Path


def test_a_route_module_imports_on_its_own():
    """``require_permissions`` validates at import time, so discovery has to have run.

    Importing a route module directly is how Alembic, a worker or a script reaches
    the app, and it must not depend on something else importing ``src.modules`` first.
    """
    result = _in_a_cold_process("import src.modules.user.routes")

    assert result.returncode == 0, result.stderr


def _in_a_cold_process(code: str) -> subprocess.CompletedProcess[str]:
    """Run ``code`` in a process that has imported nothing of the app yet."""
    backend = Path(__file__).resolve().parents[4]

    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=backend,
        capture_output=True,
        text=True,
        env={
            "PATH": "/usr/bin:/bin",
            "PYTHONPATH": str(backend),
            "SECRET_KEY": "test_secret_key_for_tests_with_32_bytes_at_least",
            "SESSION_BACKEND": "memory",
            "RATE_LIMITER_BACKEND": "memory",
        },
    )
