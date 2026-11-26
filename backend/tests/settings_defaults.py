"""Reading a setting's default, whatever the environment the suite runs in.

A default is only a default where nothing sets the variable, and the suite sets several of
them before it imports the app. Settings read the environment when they're built, so each
read builds them in this environment minus the variable being asked about.
"""

import os
from unittest.mock import patch

from src.infrastructure.config.settings import Settings


def declared_default(name: str, **environment: str) -> str:
    """The value ``Settings`` gives ``name`` when nothing sets it, as a string."""
    inherited = {key: value for key, value in os.environ.items() if key != name}
    with patch.dict(os.environ, {**inherited, **environment}, clear=True):
        return str(getattr(Settings(), name))
