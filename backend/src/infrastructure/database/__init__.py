from typing import Any

from .initialize import close_database
from .session import Base, async_session, build_engine, dispose_engine, get_engine, get_session_factory, local_session

__all__ = [
    "Base",
    "async_session",
    "build_engine",
    "close_database",
    "dispose_engine",
    "get_engine",
    "get_session_factory",
    "local_session",
]


def __getattr__(name: str) -> Any:
    """Keep the deprecated package-level ``engine`` importable; new code calls ``get_engine()``."""
    if name == "engine":
        return get_engine()

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
