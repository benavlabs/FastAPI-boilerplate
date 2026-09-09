"""Task dependencies for taskiq integration."""

from collections.abc import AsyncGenerator
from typing import Annotated

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool
from taskiq import TaskiqDepends

from ..database.session import build_engine

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_taskiq_engine() -> AsyncEngine:
    """Return the worker's engine, creating it on first use.

    Workers keep an engine separate from the API's: ``NullPool`` means a task
    connects when it needs to and hands the connection back when it is done,
    rather than holding a pool open between tasks.

    Returns:
        AsyncEngine: The worker-wide engine.
    """
    global _engine
    if _engine is None:
        _engine = build_engine(poolclass=NullPool)

    return _engine


def get_taskiq_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the session factory bound to the worker's engine.

    Returns:
        async_sessionmaker[AsyncSession]: Factory creating sessions on the
            worker's engine.
    """
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(bind=get_taskiq_engine(), class_=AsyncSession, expire_on_commit=False)

    return _session_factory


async def dispose_taskiq_engine() -> None:
    """Drain the worker engine's connections, if an engine was ever created.

    Returns without building anything when no task touched the database, so the
    worker shutdown handler can call this unconditionally. As with the API's
    engine, the object is kept and only its connections are released.
    """
    if _engine is None:
        return

    await _engine.dispose()


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Get a database session for taskiq tasks.

    Provides a database session with proper lifecycle management for
    taskiq tasks, ensuring clean connection handling and transaction management.

    Yields:
        AsyncSession: Database session configured for taskiq usage.
    """
    async with get_taskiq_session_factory()() as session:
        try:
            yield session
        finally:
            await session.close()


DBSession = Annotated[AsyncSession, TaskiqDepends(get_db_session)]
