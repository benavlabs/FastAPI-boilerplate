"""Module for tearing down the database resources."""

from .session import dispose_engine


async def close_database() -> None:
    """Close all database connections, if the engine was ever created."""
    await dispose_engine()
