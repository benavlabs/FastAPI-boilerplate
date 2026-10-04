"""One-off repair for API key rows that hold a JSON null where an object belongs.

Run it once after upgrading, from ``backend/``:

    python scripts/cleanup_api_key_json.py
"""

import asyncio
import sys
from pathlib import Path
from typing import Any, cast

backend_dir = Path(__file__).parent.parent
sys.path.append(str(backend_dir))

from sqlalchemy import CursorResult, Text, or_, update  # noqa: E402
from sqlalchemy import cast as sql_cast  # noqa: E402
from sqlalchemy.exc import SQLAlchemyError  # noqa: E402
from sqlalchemy.orm import InstrumentedAttribute  # noqa: E402
from sqlalchemy.sql.elements import ColumnElement  # noqa: E402

from scripts.seed_errors import SeedError  # noqa: E402
from src.infrastructure.database.initialize import close_database  # noqa: E402
from src.infrastructure.database.registry import import_models  # noqa: E402
from src.infrastructure.database.session import local_session  # noqa: E402
from src.infrastructure.logging import get_logger  # noqa: E402
from src.modules.api_keys.models import APIKey  # noqa: E402

logger = get_logger()

REPAIRED_COLUMNS = ("permissions", "usage_limits")


def _holds_no_object(column: InstrumentedAttribute[Any]) -> ColumnElement[bool]:
    """Rows whose ``column`` is a JSON null, or the SQL null an older schema allowed."""
    return or_(column.is_(None), sql_cast(column, Text) == "null")


async def cleanup_api_key_json() -> dict[str, int]:
    """Set every API key's null ``permissions`` and ``usage_limits`` to an empty object.

    Returns how many rows each column was repaired in.
    """
    import_models()

    repaired: dict[str, int] = {}
    async with local_session() as session:
        try:
            for name in REPAIRED_COLUMNS:
                column = getattr(APIKey, name)
                changed = await session.execute(update(APIKey).where(_holds_no_object(column)).values({column: {}}))
                repaired[name] = cast("CursorResult[Any]", changed).rowcount
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
