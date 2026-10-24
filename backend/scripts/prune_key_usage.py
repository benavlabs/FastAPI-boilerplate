"""Delete the API key usage rows past the retention.

Run it from ``backend/``, from a system cron where the project carries no worker:

    python scripts/prune_key_usage.py

``KEY_USAGE_RETENTION_DAYS`` says how many days of rows to keep, and 0 keeps every one of
them. A project with the taskiq feature has the same prune as a scheduled task instead.
"""

import asyncio
import sys
from pathlib import Path

backend_dir = Path(__file__).parent.parent
sys.path.append(str(backend_dir))

from sqlalchemy.exc import SQLAlchemyError  # noqa: E402

from scripts.seed_errors import SeedError  # noqa: E402
from src.infrastructure.database.initialize import close_database  # noqa: E402
from src.infrastructure.database.registry import import_models  # noqa: E402
from src.infrastructure.database.session import local_session  # noqa: E402
from src.infrastructure.logging import get_logger  # noqa: E402
from src.modules.api_keys.retention import prune_key_usage, retention_cutoff  # noqa: E402

logger = get_logger()


async def prune_usage_rows() -> int:
    """Delete the usage rows past ``KEY_USAGE_RETENTION_DAYS``.

    Returns:
        How many rows were deleted, and 0 where the retention keeps every row.

    Raises:
        SeedError: The rows could not be read or deleted.
    """
    import_models()

    cutoff = retention_cutoff()
    if cutoff is None:
        logger.info("KEY_USAGE_RETENTION_DAYS is 0, so nothing is configured to prune.")

        return 0

    async with local_session() as session:
        try:
            return await prune_key_usage(session, cutoff)
        except (OSError, SQLAlchemyError) as error:
            raise SeedError(f"Could not prune the usage rows: {type(error).__name__}") from error


async def main() -> None:
    try:
        await prune_usage_rows()
    except SeedError as error:
        logger.error(str(error))
        raise SystemExit(1) from error
    finally:
        await close_database()


if __name__ == "__main__":
    asyncio.run(main())
