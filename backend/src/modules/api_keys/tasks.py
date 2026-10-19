"""The scheduled prune of the usage rows a key's requests wrote."""

from ...infrastructure.logging import get_logger
from ...infrastructure.taskiq.brokers import default_broker
from ...infrastructure.taskiq.deps import DBSession
from .retention import prune_key_usage, retention_cutoff

logger = get_logger()

PRUNE_TASK_NAME = "api_keys:prune_usage"

PRUNE_CRON = "0 3 * * *"
"""When the scheduler enqueues the prune: once a day, at 03:00 UTC."""


@default_broker.task(task_name=PRUNE_TASK_NAME, schedule=[{"cron": PRUNE_CRON}])
async def prune_usage(db: DBSession) -> int:
    """Delete the usage rows past ``KEY_USAGE_RETENTION_DAYS``, and answer how many.

    Returns 0 without reading a row where the retention keeps every row.
    """
    cutoff = retention_cutoff()
    if cutoff is None:
        logger.info("KEY_USAGE_RETENTION_DAYS is 0, so every API key usage row is kept")

        return 0

    return await prune_key_usage(db, cutoff)
