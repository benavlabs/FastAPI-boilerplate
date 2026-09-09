from collections.abc import AsyncGenerator
from typing import Any

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, MappedAsDataclass

from ..config.settings import get_settings

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def build_engine(**overrides: Any) -> AsyncEngine:
    """Create a new engine for the configured database.

    Every engine in the application is built here so that pool defaults and the
    connection URL are resolved in one place. Callers that need different pooling
    (the taskiq worker uses ``NullPool``) pass it through ``overrides``.

    Args:
        **overrides: Keyword arguments forwarded to ``create_async_engine``,
            overriding the defaults below.

    Returns:
        AsyncEngine: A new, unshared engine.

    Note:
        The ``pool_size`` and ``max_overflow`` defaults are only applied when the
        caller does not choose its own ``poolclass``, because pools that do not
        queue connections reject those arguments.
    """
    settings = get_settings()
    options: dict[str, Any] = {
        "echo": False,
        "future": True,
        "pool_pre_ping": settings.POSTGRES_POOL_PRE_PING,
        "pool_recycle": settings.POSTGRES_POOL_RECYCLE,
    }
    if "poolclass" not in overrides:
        options["pool_size"] = settings.POSTGRES_POOL_SIZE
        options["max_overflow"] = settings.POSTGRES_MAX_OVERFLOW
    options.update(overrides)

    return create_async_engine(settings.DATABASE_URL, **options)


def get_engine() -> AsyncEngine:
    """Return the engine shared by the application, creating it on first use.

    The engine is created lazily so that importing this module never opens a
    connection pool. Processes that never touch the database, such as one-off
    scripts and test collection, therefore pay nothing for the import.

    Returns:
        AsyncEngine: The process-wide engine.
    """
    global _engine
    if _engine is None:
        _engine = build_engine()

    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the session factory bound to the shared engine.

    Returns:
        async_sessionmaker[AsyncSession]: Factory creating sessions on the
            process-wide engine.
    """
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(bind=get_engine(), class_=AsyncSession, expire_on_commit=False)

    return _session_factory


def local_session() -> AsyncSession:
    """Open a new session on the shared engine.

    Returns:
        AsyncSession: A session that has not been entered yet.

    Example:
        ```python
        async with local_session() as db:
            result = await db.execute(select(User))
        ```
    """
    return get_session_factory()()


async def dispose_engine() -> None:
    """Drain the shared engine's connection pool, if one was ever created.

    Returns without building anything when the engine has not been used, so
    shutdown paths can call this unconditionally.

    Note:
        The engine object itself is kept, only its pool is drained. Long-lived
        holders of the engine, such as the SQLAdmin interface, therefore keep
        working against the same engine and the process never ends up with two
        pools open at once.
    """
    if _engine is None:
        return

    await _engine.dispose()


class Base(DeclarativeBase, MappedAsDataclass):
    """Base class for all database models with comprehensive functionality.

    This base class combines SQLAlchemy's DeclarativeBase with MappedAsDataclass
    to provide a powerful foundation for all database models in the application.

    Features:
    - Automatic dataclass generation from SQLAlchemy models
    - Type-safe model definitions with Mapped annotations
    - Consistent model structure across the application
    - Built-in serialization capabilities
    - Integration with modern SQLAlchemy patterns

    Note:
        All database models should inherit from this base class to ensure
        consistent behavior and access to shared functionality.

        The MappedAsDataclass mixin automatically generates dataclass
        methods (__init__, __repr__, __eq__, etc.) based on the model's
        mapped columns.

    Example:
        ```python
        from sqlalchemy.orm import Mapped, mapped_column
        from sqlalchemy import String, Integer

        class User(Base):
            __tablename__ = "users"

            id: Mapped[int] = mapped_column(Integer, primary_key=True)
            name: Mapped[str] = mapped_column(String(100))
            email: Mapped[str] = mapped_column(String(255), unique=True)

        # Usage
        user = User(name="John Doe", email="john@example.com")
        ```
    """

    pass


async def async_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for database session management with proper lifecycle.

    This function provides an async database session for use in FastAPI
    dependencies and other async contexts. It ensures proper session
    lifecycle management with automatic cleanup.

    Yields:
        AsyncSession: A configured async database session.

    Note:
        This function is designed to be used as a FastAPI dependency
        via Depends(async_session). It automatically handles session
        creation, lifecycle management, and cleanup.

        The session is configured with:
        - expire_on_commit=False for better performance
        - Automatic transaction management
        - Proper cleanup on context exit

    Example:
        ```python
        from fastapi import Depends
        from sqlalchemy.ext.asyncio import AsyncSession

        @app.get("/users/")
        async def get_users(db: AsyncSession = Depends(async_session)):
            result = await db.execute(select(User))
            return result.scalars().all()
        ```
    """
    async_get_db = local_session
    async with async_get_db() as db:
        yield db


async def create_tables() -> None:
    """Create all tables in the database if they don't exist.

    This function creates all database tables defined by the models
    that inherit from the Base class. It's typically used during
    application initialization or database setup.

    Note:
        This function is idempotent - it will only create tables that
        don't already exist. Existing tables are left unchanged.

        The function uses SQLAlchemy's metadata.create_all() method
        within an async transaction for safe table creation.

        For production deployments, consider using migration tools
        like Alembic instead of this function for better control
        over database schema changes.

    Example:
        ```python
        # In application startup
        async def startup_event():
            await create_tables()
            logger.info("Database tables created successfully")

        # Or in a setup script
        if __name__ == "__main__":
            import asyncio
            asyncio.run(create_tables())
        ```
    """
    async with get_engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


def __getattr__(name: str) -> AsyncEngine:
    """Resolve the legacy module-level ``engine`` attribute.

    Backward compatibility only: ``engine`` used to be a module-level object, so
    forks still import it directly. New code calls ``get_engine()`` instead.
    Remove this at the next major version.

    Args:
        name: Attribute being looked up on this module.

    Returns:
        AsyncEngine: The shared engine when ``name`` is ``"engine"``.

    Raises:
        AttributeError: For every other name.
    """
    if name == "engine":
        return get_engine()

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
