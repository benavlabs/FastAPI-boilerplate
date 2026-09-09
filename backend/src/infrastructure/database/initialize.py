"""Module for tearing down the database resources."""

from .session import dispose_engine


async def close_database() -> None:
    """Close all database connections.

    This function should be called during application shutdown to clean up resources.
    It is a no-op when the engine was never created, so no pool is opened just to be
    disposed.
    """
    await dispose_engine()
