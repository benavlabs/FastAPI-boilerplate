import asyncio
import sys
from pathlib import Path

backend_dir = Path(__file__).parent.parent
sys.path.append(str(backend_dir))

from scripts.seeders import SEEDERS  # noqa: E402
from src.infrastructure.database.initialize import close_database  # noqa: E402
from src.infrastructure.database.session import create_tables  # noqa: E402
from src.infrastructure.logging import get_logger  # noqa: E402

logger = get_logger()


async def setup_initial_data() -> None:
    """
    Setup initial data for the application:
    - Create database tables
    - Run each selected feature's seeder, in the order ``scripts/seeders.py`` lists
      them: the default tier, then the first superuser.
    """
    logger.info("Setting up initial data...")

    logger.info("Creating database tables...")
    await create_tables()
    logger.info("Database tables created successfully")

    for seed in SEEDERS:
        logger.info(f"Running {seed.__name__}...")
        await seed()

    logger.info("Initial data setup complete")


async def main() -> None:
    try:
        await setup_initial_data()
    except Exception as error:
        logger.error(f"Initial data setup failed: {error}")
        raise SystemExit(1) from error
    finally:
        await close_database()


if __name__ == "__main__":
    asyncio.run(main())
