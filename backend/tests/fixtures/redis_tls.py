"""What a feature's Redis connection speaks, read in a fresh process."""

import os
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]


def connection_in_a_fresh_process(feature_environment: dict[str, str], imports: str, shown: str) -> list[str]:
    """Import with the feature's own variables set and print ``shown``, the values separated by ``|``."""
    environment = {
        **os.environ,
        "ENVIRONMENT": "local",
        "SECRET_KEY": "a-key-only-this-test-runs-with",
        **feature_environment,
    }
    run = subprocess.run(
        [sys.executable, "-c", f"{imports}; print(*({shown}), sep='|')"],
        cwd=BACKEND,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert run.returncode == 0, run.stderr[-2000:]

    return run.stdout.strip().splitlines()[-1].split("|")


def spoken(ssl: bool) -> list[str]:
    """The connection class and the URL scheme a connection with ``ssl`` shows."""
    return ["SSLConnection", "rediss"] if ssl else ["Connection", "redis"]
