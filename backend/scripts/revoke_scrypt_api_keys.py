"""Name the API keys still stored under a scrypt hash, and revoke them when asked.

Run it from ``backend/``:

    python scripts/revoke_scrypt_api_keys.py
    python scripts/revoke_scrypt_api_keys.py --revoke

A key minted before keys were stored as a digest holds a salted scrypt hash, and the
first request that authenticates it rewrites the row as a digest. Until then, a request
carrying that key's prefix costs the server one derivation, and a prefix is listed to its
owner, so a key nobody is using keeps that cost available to anybody who holds it.

Without ``--revoke`` the keys are only reported, so their owners can be told to mint new
ones. With it they are deactivated, which ends the cost: a revoked row is not derived
against.
"""

import asyncio
import sys
from pathlib import Path
from typing import Any, cast

backend_dir = Path(__file__).parent.parent
sys.path.append(str(backend_dir))

from sqlalchemy import CursorResult, select, update  # noqa: E402
from sqlalchemy.exc import SQLAlchemyError  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from scripts.seed_errors import SeedError  # noqa: E402
from src.infrastructure.database.initialize import close_database  # noqa: E402
from src.infrastructure.database.registry import import_models  # noqa: E402
from src.infrastructure.database.session import local_session  # noqa: E402
from src.infrastructure.logging import get_logger  # noqa: E402
from src.modules.api_keys.models import APIKey  # noqa: E402
from src.modules.api_keys.service import SCRYPT_SCHEME  # noqa: E402

logger = get_logger()

STORED_AS_SCRYPT = f"{SCRYPT_SCHEME}$"

REVOKE = "--revoke"
USAGE = f"Usage: python scripts/revoke_scrypt_api_keys.py [{REVOKE}]"


async def _report(session: AsyncSession) -> int:
    """Name every key still holding a scrypt hash, and how many there are.

    What is named is what an owner needs to find the key in a listing of their own: the
    prefix, the name it was minted under, and when it was last used.
    """
    found = await session.execute(
        select(APIKey.id, APIKey.user_id, APIKey.name, APIKey.key_prefix, APIKey.is_active, APIKey.last_used_at)
        .where(APIKey.key_hash.startswith(STORED_AS_SCRYPT))
        .order_by(APIKey.id)
    )
    held = found.all()
    for key in held:
        logger.info(
            f"API key {key.id} of user {key.user_id} is stored as scrypt: {key.name!r}, "
            f"prefix {key.key_prefix}, active {key.is_active}, last used {key.last_used_at}"
        )

    return len(held)


async def _revoke(session: AsyncSession) -> int:
    """Deactivate every key still holding a scrypt hash, and how many of them that changed.

    A key already revoked is left as it is, so a second run revokes nothing.

    Raises:
        SeedError: The keys could not be revoked.
    """
    try:
        deactivated = await session.execute(
            update(APIKey).where(APIKey.key_hash.startswith(STORED_AS_SCRYPT), APIKey.is_active).values(is_active=False)
        )
        await session.commit()
    except (OSError, SQLAlchemyError) as error:
        raise SeedError(f"Could not revoke the API keys stored as scrypt: {type(error).__name__}") from error

    return cast("CursorResult[Any]", deactivated).rowcount


async def revoke_scrypt_api_keys(revoking: bool = False) -> tuple[int, int]:
    """Report the keys still stored as scrypt, deactivating them where ``revoking``.

    Returns:
        How many keys are stored as scrypt, and how many of them this run revoked.

    Raises:
        SeedError: The keys could not be read or revoked.
    """
    import_models()

    async with local_session() as session:
        try:
            stored = await _report(session)
        except (OSError, SQLAlchemyError) as error:
            raise SeedError(f"Could not read the API keys stored as scrypt: {type(error).__name__}") from error

        revoked = await _revoke(session) if revoking else 0

    logger.info(f"API keys stored as scrypt: {stored}, revoked: {revoked}")

    return stored, revoked


async def main() -> None:
    if sys.argv[1:] not in ([], [REVOKE]):
        logger.error(USAGE)
        raise SystemExit(2)

    try:
        await revoke_scrypt_api_keys(revoking=sys.argv[1:] == [REVOKE])
    except SeedError as error:
        logger.error(str(error))
        raise SystemExit(1) from error
    finally:
        await close_database()


if __name__ == "__main__":
    asyncio.run(main())
