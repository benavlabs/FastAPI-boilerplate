"""How long a key's usage rows are kept, and deleting the ones past it."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.config.settings import get_settings
from ...infrastructure.logging import get_logger
from .models import KeyUsage

logger = get_logger()

PRUNE_BATCH_SIZE = 10_000
"""How many rows one DELETE takes."""

ANALYTICS_MAX_DAYS = 365
"""The widest window the analytics read where no row is pruned."""


def retention_cutoff() -> datetime | None:
    """The moment before which a row is past the retention, or ``None`` where every row is kept."""
    days = get_settings().KEY_USAGE_RETENTION_DAYS
    if days == 0:
        return None

    return datetime.now(UTC) - timedelta(days=days)


def retained_days() -> int:
    """How many days back the rows still reach, at most ``ANALYTICS_MAX_DAYS``."""
    days = get_settings().KEY_USAGE_RETENTION_DAYS
    if days == 0:
        return ANALYTICS_MAX_DAYS

    return min(days, ANALYTICS_MAX_DAYS)


async def prune_key_usage(db: AsyncSession, older_than: datetime) -> int:
    """Delete the usage rows written before ``older_than``, ``PRUNE_BATCH_SIZE`` at a time.

    Each batch is committed on its own, and the last one is the batch that comes back
    short. The keys themselves are left alone, ``last_used_at`` and ``last_used_ip``
    included.

    Returns:
        How many rows were deleted.
    """
    pruned = 0

    while True:
        found = await db.execute(select(KeyUsage.id).where(KeyUsage.created_at < older_than).limit(PRUNE_BATCH_SIZE))
        batch = list(found.scalars())
        if batch:
            await db.execute(delete(KeyUsage).where(KeyUsage.id.in_(batch)))
            await db.commit()
            pruned += len(batch)

        if len(batch) < PRUNE_BATCH_SIZE:
            break

    logger.info(f"Pruned {pruned} API key usage rows written before {older_than.isoformat()}")

    return pruned
