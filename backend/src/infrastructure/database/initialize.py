"""Module for tearing down the database resources."""

from .session import engine


async def close_database() -> None:
    """Close all database connections.

    This function should be called during application shutdown to clean up resources.
    """
    await engine.dispose()
