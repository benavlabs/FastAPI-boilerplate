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
    """Resolve the legacy package-level ``engine`` attribute.

    Backward compatibility only, mirroring the shim in ``session``. New code calls
    ``get_engine()``. Remove this at the next major version.

    Args:
        name: Attribute being looked up on this package.

    Returns:
        Any: The shared engine when ``name`` is ``"engine"``.

    Raises:
        AttributeError: For every other name.
    """
    if name == "engine":
        return get_engine()

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
