"""One-off repair for user rows whose address was stored with case or whitespace in it.

Run it once after upgrading, from ``backend/``:

    python scripts/canonicalize_emails.py

It refuses, naming them, while two accounts hold one address once case and whitespace are
ignored. Otherwise it rewrites every address into the form every lookup uses, adds the unique
index over it, and can be run again.
"""

import asyncio
import sys
from collections import Counter
from pathlib import Path

backend_dir = Path(__file__).parent.parent
sys.path.append(str(backend_dir))

from crudauth.utils import canonical_email  # noqa: E402
from sqlalchemy import select, text, update  # noqa: E402
from sqlalchemy.exc import SQLAlchemyError  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from scripts.seed_errors import SeedError  # noqa: E402
from src.infrastructure.database.initialize import close_database  # noqa: E402
from src.infrastructure.database.registry import import_models  # noqa: E402
from src.infrastructure.database.session import local_session  # noqa: E402
from src.infrastructure.logging import get_logger  # noqa: E402
from src.modules.user.models import User  # noqa: E402

logger = get_logger()

INDEX_NAME = "ix_user_email_lower"
CREATE_INDEX = f'CREATE UNIQUE INDEX IF NOT EXISTS {INDEX_NAME} ON "user" (lower(email))'


async def _stored(session: AsyncSession) -> list[tuple[int, str]]:
    """Every account's id and address, as they are stored."""
    rows = await session.execute(select(User.id, User.email))

    return [(identifier, email) for identifier, email in rows]


def _held_by_two_accounts(stored: list[tuple[int, str]]) -> list[str]:
    """The canonical addresses that more than one row would end up holding.

    Canonicalising with ``crudauth``'s own function is what makes this agree with the
    app: Python's ``strip()`` takes tabs and newlines, which Postgres ``btrim`` leaves.
    """
    held = Counter(canonical_email(email) for _, email in stored)

    return sorted(address for address, accounts in held.items() if accounts > 1)


async def canonicalize_emails() -> int:
    """Rewrite every stored address into its canonical form, then make that form unique.

    Returns how many rows were rewritten.

    Raises:
        SeedError: two accounts hold one address once case and whitespace are ignored, or
            the database could not be read or written.
    """
    import_models()

    async with local_session() as session:
        try:
            stored = await _stored(session)
            shared = _held_by_two_accounts(stored)
            if shared:
                raise SeedError(
                    f"{len(shared)} address(es) are held by more than one account once case and "
                    f"whitespace are ignored: {', '.join(shared)}. Merge or rename those accounts "
                    "first: which one keeps the address is not a decision this script can make."
                )

            rewrites = [
                {"id": identifier, "email": canonical_email(email)}
                for identifier, email in stored
                if email != canonical_email(email)
            ]
            if rewrites:
                await session.execute(update(User), rewrites)
            await session.execute(text(CREATE_INDEX))
            await session.commit()
        except SQLAlchemyError as error:
            raise SeedError(f"Could not canonicalize the stored addresses: {type(error).__name__}") from error

    logger.info(f"Addresses rewritten: {len(rewrites)}. {INDEX_NAME} is in place.")

    return len(rewrites)


async def main() -> None:
    try:
        await canonicalize_emails()
    except SeedError as error:
        logger.error(str(error))
        raise SystemExit(1) from error
    finally:
        await close_database()


if __name__ == "__main__":
    asyncio.run(main())
