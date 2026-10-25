"""Reading a setting's declared default, whatever the environment the suite runs in.

A default is only a default where nothing sets the variable, and the suite sets several of
them before it imports the app. So each read happens in a fresh interpreter whose
environment is this one minus the variable being asked about.
"""

import os
import subprocess
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]

_DECLARED_DEFAULT = """
from src.infrastructure.config.settings import Settings

print("DEFAULT:" + str(Settings.model_fields[{name!r}].default))
"""


def declared_default(name: str, **environment: str) -> str:
    """``Settings``' declared default for ``name``, as a string."""
    inherited = {key: value for key, value in os.environ.items() if key != name}
    result = subprocess.run(
        [sys.executable, "-c", _DECLARED_DEFAULT.format(name=name)],
        cwd=BACKEND_ROOT,
        capture_output=True,
        text=True,
        check=True,
        env={**inherited, **environment},
    )
    line = next(line for line in result.stdout.splitlines() if line.startswith("DEFAULT:"))

    return line.removeprefix("DEFAULT:")
