import asyncio
import sys
from pathlib import Path

# Add the backend directory to Python path
backend_dir = Path(__file__).parent.parent
sys.path.append(str(backend_dir))

from sqlalchemy import select  # noqa: E402

from src.infrastructure.config.settings import settings  # noqa: E402
from src.infrastructure.database.initialize import close_database  # noqa: E402
from src.infrastructure.database.session import local_session  # noqa: E402
from src.infrastructure.logging import get_logger  # noqa: E402
from src.modules.tier.models import Tier  # noqa: E402

logger = get_logger()


async def create_first_tier() -> None:
    """
    Create the first tier in the database if it doesn't exist.

    This script uses environment variables for configuration:
    - DEFAULT_TIER_NAME: The name of the default tier (defaults to "free")
    """
    try:
        tier_name = getattr(settings, "DEFAULT_TIER_NAME", "free")

        async with local_session() as session:
            query = select(Tier).where(Tier.name == tier_name)
            result = await session.execute(query)
            tier = result.scalar_one_or_none()

            if tier:
                logger.info(f"Tier '{tier_name}' already exists with ID {tier.id}")
                return

            tier = Tier(name=tier_name)
            session.add(tier)
            await session.commit()
            await session.refresh(tier)

            logger.info(f"Tier '{tier_name}' created successfully with ID {tier.id}")

    except Exception as e:
        logger.error(f"Error creating tier: {e}")


async def main() -> None:
    try:
        await create_first_tier()
    finally:
        await close_database()


if __name__ == "__main__":
    asyncio.run(main())
