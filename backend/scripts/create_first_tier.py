import asyncio
import sys
from pathlib import Path

# Add the backend directory to Python path
backend_dir = Path(__file__).parent.parent
sys.path.append(str(backend_dir))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.exc import SQLAlchemyError  # noqa: E402

from scripts.seed_errors import SeedError  # noqa: E402
from src.infrastructure.config.settings import settings  # noqa: E402
from src.infrastructure.database.initialize import close_database  # noqa: E402
from src.infrastructure.database.registry import import_models  # noqa: E402
from src.infrastructure.database.session import local_session  # noqa: E402
from src.infrastructure.logging import get_logger  # noqa: E402
from src.modules.tier.models import Tier  # noqa: E402

logger = get_logger()


async def create_first_tier() -> None:
    """Create the default tier named by DEFAULT_TIER_NAME, if it isn't there yet."""
    tier_name = settings.DEFAULT_TIER_NAME

    import_models()

    async with local_session() as session:
        query = select(Tier).where(Tier.name == tier_name)

        try:
            result = await session.execute(query)
            tier = result.scalar_one_or_none()

            if tier:
                logger.info(f"Tier '{tier_name}' already exists with ID {tier.id}")
                return

            tier = Tier(name=tier_name)
            session.add(tier)
            await session.commit()
            await session.refresh(tier)
        except (OSError, SQLAlchemyError) as error:
            raise SeedError(f"Could not seed the tier '{tier_name}': {type(error).__name__}") from error

        logger.info(f"Tier '{tier_name}' created successfully with ID {tier.id}")


async def main() -> None:
    try:
        await create_first_tier()
    except SeedError as error:
        logger.error(str(error))
        raise SystemExit(1) from error
    finally:
        await close_database()


if __name__ == "__main__":
    asyncio.run(main())
