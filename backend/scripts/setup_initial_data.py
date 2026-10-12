import asyncio
import sys
from pathlib import Path

backend_dir = Path(__file__).parent.parent
sys.path.append(str(backend_dir))

from scripts.seeders import SEEDERS  # noqa: E402
from src.infrastructure.config.settings import settings  # noqa: E402
from src.infrastructure.database.health import every_declared_table_exists  # noqa: E402
from src.infrastructure.database.initialize import close_database  # noqa: E402
from src.infrastructure.database.session import create_tables  # noqa: E402
from src.infrastructure.logging import get_logger  # noqa: E402

logger = get_logger()


async def setup_initial_data() -> None:
    """
    Setup initial data for the application:
    - Create database tables, where this project creates its own
    - Run each selected feature's seeder, in the order ``scripts/seeders.py`` lists
      them: the default tier, then the first superuser.

    Where ``CREATE_TABLES_ON_STARTUP`` is off, migrations own the schema, and creating
    tables here would write them behind alembic's back: a baseline applied afterwards
    fails on the first table that already exists. The migrations have to have run first,
    so a schema that isn't there ends the run before a seeder reaches for a table.

    Raises:
        SystemExit: The schema is missing and this project doesn't create it.
    """
    logger.info("Setting up initial data...")

    if settings.CREATE_TABLES_ON_STARTUP:
        logger.info("Creating database tables...")
        await create_tables()
        logger.info("Database tables created successfully")
    else:
        logger.info("CREATE_TABLES_ON_STARTUP is off, so the schema is alembic's; creating no tables")
        try:
            await every_declared_table_exists()
        except RuntimeError as error:
            raise SystemExit(f"Not seeding: {error}. Run `alembic upgrade head` first.") from error

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
