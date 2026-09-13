import asyncio
import sys
from pathlib import Path

backend_dir = Path(__file__).parent.parent
sys.path.append(str(backend_dir))

from scripts.create_first_superuser import create_first_superuser  # noqa: E402
from scripts.create_first_tier import create_first_tier  # noqa: E402
from src.infrastructure.database.initialize import close_database  # noqa: E402
from src.infrastructure.database.session import create_tables  # noqa: E402
from src.infrastructure.logging import get_logger  # noqa: E402

logger = get_logger()


async def setup_initial_data() -> None:
    """
    Setup initial data for the application, including:
    - Create database tables
    - Create default tier
    - Create admin superuser
    """
    logger.info("Setting up initial data...")

    logger.info("Creating database tables...")
    try:
        await create_tables()
        logger.info("Database tables created successfully")
    except Exception as e:
        logger.error(f"Error creating database tables: {str(e)}", exc_info=True)
        sys.exit(1)

    logger.info("Creating first tier...")
    await create_first_tier()

    logger.info("Creating superuser...")
    await create_first_superuser()

    logger.info("Initial data setup complete")


async def main() -> None:
    try:
        await setup_initial_data()
    finally:
        await close_database()


if __name__ == "__main__":
    asyncio.run(main())
