"""One-off repair for API key rows whose JSON columns hold something nothing can read.

Run it once after upgrading, from ``backend/``:

    python scripts/cleanup_api_key_json.py
"""

import asyncio
import sys
from pathlib import Path
from typing import Any, cast

backend_dir = Path(__file__).parent.parent
sys.path.append(str(backend_dir))

from sqlalchemy import CursorResult, Text, func, or_, select, update  # noqa: E402
from sqlalchemy import cast as sql_cast  # noqa: E402
from sqlalchemy.dialects.postgresql import JSON  # noqa: E402
from sqlalchemy.exc import SQLAlchemyError  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402
from sqlalchemy.orm import InstrumentedAttribute  # noqa: E402
from sqlalchemy.sql.elements import ColumnElement  # noqa: E402

from scripts.seed_errors import SeedError  # noqa: E402
from src.infrastructure.database.initialize import close_database  # noqa: E402
from src.infrastructure.database.registry import import_models  # noqa: E402
from src.infrastructure.database.session import local_session  # noqa: E402
from src.infrastructure.logging import get_logger  # noqa: E402
from src.modules.api_keys.limits import countable  # noqa: E402
from src.modules.api_keys.models import APIKey  # noqa: E402

logger = get_logger()

SCOPE_COLUMN = "permissions"
LIMITS_COLUMN = "usage_limits"


def _holds_no_object(column: InstrumentedAttribute[Any]) -> ColumnElement[bool]:
    """Rows whose ``column`` is a JSON null, or the SQL null an older schema allowed."""
    return or_(column.is_(None), sql_cast(column, Text) == "null")


def _is_not_a_list(column: InstrumentedAttribute[Any]) -> ColumnElement[bool]:
    """Rows whose ``column`` holds anything but a JSON array, the scope object included."""
    return or_(_holds_no_object(column), func.json_typeof(sql_cast(column, JSON)) != "array")


async def _repair_scopes(session: AsyncSession) -> int:
    """Empty every scope that isn't a JSON array, the object an older version stored included.

    Such a scope names nothing the permission registry knows, so the key is left unscoped.
    """
    changed = await session.execute(update(APIKey).where(_is_not_a_list(APIKey.permissions)).values({APIKey.permissions: []}))

    return cast("CursorResult[Any]", changed).rowcount


def _dropped(limits: Any, usable: dict[str, int]) -> Any:
    """What the repair takes out of ``limits``: the entries it can't count, or the whole value."""
    if not isinstance(limits, dict):
        return limits

    return {name: value for name, value in limits.items() if name not in usable}


async def _repair_limits(session: AsyncSession) -> int:
    """Rewrite every usage limit the limiter can't count, keeping the windows it can.

    A limit stored under a name no window counts, or with a value that isn't a positive
    whole number of requests, enforces nothing. Dropping just those leaves the limits a
    project meant and can have enforced; a value that isn't an object at all becomes one.

    What each row loses is logged: none of it was being enforced, but a project that meant
    ``{"requests_per_day": "1000"}`` would otherwise have no record of what to set again.
    """
    stored = await session.execute(select(APIKey.id, APIKey.usage_limits))

    repaired = 0
    for api_key_id, limits in stored.all():
        usable = countable(limits) if isinstance(limits, dict) else {}
        if usable == limits:
            continue

        await session.execute(update(APIKey).where(APIKey.id == api_key_id).values({APIKey.usage_limits: usable}))
        logger.info(f"API key {api_key_id}: dropped usage limits {_dropped(limits, usable)!r}, kept {usable!r}")
        repaired += 1

    return repaired


async def cleanup_api_key_json() -> dict[str, int]:
    """Repair every API key column holding something no code can read.

    Returns how many rows each column was repaired in.
    """
    import_models()

    async with local_session() as session:
        try:
            repaired = {
                SCOPE_COLUMN: await _repair_scopes(session),
                LIMITS_COLUMN: await _repair_limits(session),
            }
            await session.commit()
        except (OSError, SQLAlchemyError) as error:
            raise SeedError(f"Could not repair the API key rows: {type(error).__name__}") from error

    logger.info("API key rows repaired: " + ", ".join(f"{name}={count}" for name, count in repaired.items()))

    return repaired


async def main() -> None:
    try:
        await cleanup_api_key_json()
    except SeedError as error:
        logger.error(str(error))
        raise SystemExit(1) from error
    finally:
        await close_database()


if __name__ == "__main__":
    asyncio.run(main())
