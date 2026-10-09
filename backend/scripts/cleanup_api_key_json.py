"""One-off repair for API key rows whose JSON columns hold something the schemas refuse.

Run it once after upgrading, from ``backend/``:

    python scripts/cleanup_api_key_json.py
"""

import asyncio
import sys
from pathlib import Path
from typing import Any, cast

backend_dir = Path(__file__).parent.parent
sys.path.append(str(backend_dir))

from sqlalchemy import CursorResult, Text, func, or_, update  # noqa: E402
from sqlalchemy import cast as sql_cast  # noqa: E402
from sqlalchemy.dialects.postgresql import JSON  # noqa: E402
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

REPAIRED_COLUMNS: dict[str, list[str] | dict[str, Any]] = {"permissions": [], "usage_limits": {}}
"""Each repaired column, with the empty value its schemas read."""


def _holds_no_object(column: InstrumentedAttribute[Any]) -> ColumnElement[bool]:
    """Rows whose ``column`` is a JSON null, or the SQL null an older schema allowed."""
    return or_(column.is_(None), sql_cast(column, Text) == "null")


def _is_not_a_list(column: InstrumentedAttribute[Any]) -> ColumnElement[bool]:
    """Rows whose ``column`` holds anything but a JSON array, the scope object included."""
    return or_(_holds_no_object(column), func.json_typeof(sql_cast(column, JSON)) != "array")


async def cleanup_api_key_json() -> dict[str, int]:
    """Empty every API key's ``permissions`` and ``usage_limits`` that its schemas refuse.

    A scope an older version stored as an object names nothing the permission registry
    knows, so the key is left unscoped.

    Returns how many rows each column was repaired in.
    """
    import_models()

    repaired: dict[str, int] = {}
    async with local_session() as session:
        try:
            for name, empty in REPAIRED_COLUMNS.items():
                column = getattr(APIKey, name)
                refused = _is_not_a_list(column) if isinstance(empty, list) else _holds_no_object(column)
                changed = await session.execute(update(APIKey).where(refused).values({column: empty}))
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
