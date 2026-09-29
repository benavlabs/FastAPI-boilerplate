import asyncio
import sys
from pathlib import Path

backend_dir = Path(__file__).parent.parent
sys.path.append(str(backend_dir))

from sqlalchemy import update  # noqa: E402

from src.infrastructure.config.settings import settings  # noqa: E402
from src.infrastructure.database.initialize import close_database  # noqa: E402
from src.infrastructure.database.session import local_session  # noqa: E402
from src.infrastructure.logging import get_logger  # noqa: E402
from src.modules.user.exceptions import UserNotFoundError  # noqa: E402
from src.modules.user.models import User  # noqa: E402
from src.modules.user.schemas import UserCreate  # noqa: E402
from src.modules.user.service import UserService  # noqa: E402

logger = get_logger()


class SeedError(RuntimeError):
    """Raised when the environment can't produce the row this script is meant to seed."""


async def create_first_superuser() -> None:
    """Create the first superuser from the admin environment variables.

    Reads ADMIN_NAME, ADMIN_EMAIL, ADMIN_USERNAME and ADMIN_PASSWORD, and raises
    when any is missing rather than falling back to a known credential.

    An account already registered with ADMIN_EMAIL is never promoted: whoever
    holds that address may not be the operator, so the caller is told to pick
    another address or promote the account deliberately.
    """
    name = settings.ADMIN_NAME
    email = settings.ADMIN_EMAIL
    username = settings.ADMIN_USERNAME
    password = settings.ADMIN_PASSWORD

    if not all([name, email, username, password]):
        raise SeedError("Set ADMIN_NAME, ADMIN_EMAIL, ADMIN_USERNAME and ADMIN_PASSWORD before seeding a superuser.")

    async with local_session() as session:
        user_service = UserService()

        try:
            existing = await user_service.get_by_email(email, session)
        except UserNotFoundError:
            existing = None

        if existing is not None:
            if existing["is_superuser"]:
                logger.info(f"Superuser {existing['username']} already exists.")
                return

            raise SeedError(
                f"{email} already belongs to user {existing['username']}, who is not a superuser. "
                "Choose another ADMIN_EMAIL, or promote that account deliberately."
            )

        created = await user_service.create(UserCreate(name=name, email=email, username=username, password=password), session)

        await session.execute(update(User).where(User.id == created["id"]).values(is_superuser=True))
        await session.commit()

        logger.info(f"Superuser {username} created successfully with ID {created['id']}")


async def main() -> None:
    try:
        await create_first_superuser()
    except SeedError as error:
        logger.error(str(error))
        raise SystemExit(1) from error
    finally:
        await close_database()


if __name__ == "__main__":
    asyncio.run(main())
