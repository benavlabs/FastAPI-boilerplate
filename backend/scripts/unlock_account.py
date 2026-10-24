"""Clear the login lockout an account is held in.

Run it from ``backend/``:

    python scripts/unlock_account.py <username-or-email>

The lockout is keyed by the identifier each login submitted, so an account can be held
under its username and under its address; both are cleared. The counters of the address
those logins came from are left alone: they belong to whoever filled them, and they
expire. An address is matched ignoring case, so one stored before addresses were
canonicalised is found; one stored with whitespace in it is not, and that account's
username still names it.

The counters live in the limiter the API uses, so this clears what a running API reads
only while that limiter is shared (``RATE_LIMITER_BACKEND=redis``, or the database
store). With the in-memory backend each API process holds its own, and only a restart
clears them.
"""

import asyncio
import sys
from pathlib import Path

backend_dir = Path(__file__).parent.parent
sys.path.append(str(backend_dir))

from crudauth.ratelimit.constants import LOCKOUT_NAMESPACE  # noqa: E402
from crudauth.utils import canonical_email, canonical_identifier  # noqa: E402
from sqlalchemy import func, or_, select  # noqa: E402
from sqlalchemy.exc import SQLAlchemyError  # noqa: E402

from scripts.seed_errors import SeedError  # noqa: E402
from src.infrastructure.auth.setup import auth  # noqa: E402
from src.infrastructure.database.initialize import close_database  # noqa: E402
from src.infrastructure.database.registry import import_models  # noqa: E402
from src.infrastructure.database.session import local_session  # noqa: E402
from src.infrastructure.logging import get_logger  # noqa: E402
from src.modules.user.models import User  # noqa: E402

logger = get_logger()

NO_SOURCE = "0.0.0.0"
"""The address the clearing is attributed to, so it takes back no address's own count."""

USAGE = "Usage: python scripts/unlock_account.py <username-or-email>"


async def _clear(identifier: str) -> None:
    """Clear what the lockout holds under ``identifier``, and read it back.

    ``record_login_success`` logs a backend failure and returns, so the read is what
    says whether the clear landed.

    Raises:
        SeedError: There is no limiter to clear, it could not be reached, or it still
            holds the lockout.
    """
    lockout = auth.runtime.lockout
    if lockout is None:
        raise SeedError("No login limiter is configured, so there is no lockout to clear.")

    await auth.runtime.record_login_success(NO_SOURCE, identifier)

    held = canonical_identifier(identifier)
    try:
        locked_for = await lockout.backend.get_ttl(f"{LOCKOUT_NAMESPACE}:lock:user:{held}")
        failures = await lockout.backend.get_count(f"{LOCKOUT_NAMESPACE}:user:{held}")
    except Exception as error:
        raise SeedError(f"Could not reach the login limiter: {type(error).__name__}") from error

    if locked_for > 0 or failures:
        raise SeedError("The limiter still holds the lock or the failures behind it, so the clear did not land.")


async def unlock_account(identifier: str) -> tuple[str, ...]:
    """Clear the login lockout on the account ``identifier`` names.

    Returns:
        The identifiers whose counters were cleared: the account's username and address.

    Raises:
        SeedError: No account holds that username or address, it could not be read, or the
            limiter could not be reached or still holds the lockout.
    """
    import_models()

    async with local_session() as session:
        try:
            found = await session.execute(
                select(User.username, User.email).where(
                    or_(User.username == identifier, func.lower(User.email) == canonical_email(identifier))
                )
            )
            account = found.first()
        except SQLAlchemyError as error:
            raise SeedError(f"Could not read the account: {type(error).__name__}") from error

    if account is None:
        raise SeedError("No account holds that username or address.")

    cleared = (str(account.username), str(account.email))
    for held in cleared:
        await _clear(held)

    logger.info(f"Login lockout cleared for {len(cleared)} identifiers of one account.")

    return cleared


async def main() -> None:
    if len(sys.argv) != 2:
        logger.error(USAGE)
        raise SystemExit(2)

    try:
        await unlock_account(sys.argv[1])
    except SeedError as error:
        logger.error(str(error))
        raise SystemExit(1) from error
    finally:
        await close_database()


if __name__ == "__main__":
    asyncio.run(main())
