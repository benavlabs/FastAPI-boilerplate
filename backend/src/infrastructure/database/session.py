from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, MappedAsDataclass

from ..config.settings import settings

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    future=True,
    pool_size=settings.POSTGRES_POOL_SIZE,
    max_overflow=settings.POSTGRES_MAX_OVERFLOW,
    pool_pre_ping=settings.POSTGRES_POOL_PRE_PING,
    pool_recycle=settings.POSTGRES_POOL_RECYCLE,
)

local_session = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)


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
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
