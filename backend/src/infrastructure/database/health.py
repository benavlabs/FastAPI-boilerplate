"""Whether the database is reachable."""

from sqlalchemy import text

from ..composition import ReadinessCheck
from ..config.settings import settings
from .session import async_session


async def database_is_reachable() -> None:
    """Raise unless a trivial statement comes back from the database."""
    async for session in async_session():
        await session.execute(text("SELECT 1"))


readiness = ReadinessCheck("database", database_is_reachable, target=lambda: settings.DATABASE_URL)
