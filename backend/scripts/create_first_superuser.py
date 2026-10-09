import asyncio
import sys
from pathlib import Path

backend_dir = Path(__file__).parent.parent
sys.path.append(str(backend_dir))

from crudauth.exceptions import PasswordPolicyException  # noqa: E402
from pydantic import ValidationError  # noqa: E402
from sqlalchemy import update  # noqa: E402
from sqlalchemy.exc import SQLAlchemyError  # noqa: E402

from scripts.seed_errors import SeedError  # noqa: E402
from src.infrastructure.config.settings import settings  # noqa: E402
from src.infrastructure.database.initialize import close_database  # noqa: E402
from src.infrastructure.database.registry import import_models  # noqa: E402
from src.infrastructure.database.session import local_session  # noqa: E402
from src.infrastructure.logging import get_logger  # noqa: E402
from src.modules.common.exceptions import DomainError  # noqa: E402
from src.modules.user.exceptions import UserNotFoundError  # noqa: E402
from src.modules.user.models import User  # noqa: E402
from src.modules.user.schemas import UserCreate  # noqa: E402
from src.modules.user.service import UserService  # noqa: E402

logger = get_logger()


SETTING_FOR_FIELD = {
    "name": "ADMIN_NAME",
    "email": "ADMIN_EMAIL",
    "username": "ADMIN_USERNAME",
    "password": "ADMIN_PASSWORD",
}


def _policy_failures(error: PasswordPolicyException) -> str:
    """The unmet rules, as one line."""
    return "; ".join(str(entry.get("msg", entry.get("type"))) for entry in error.errors)


def _setting_failures(error: ValidationError) -> str:
    """The admin settings the user payload refused, named as settings, as one line."""
    return "; ".join(
        f"{SETTING_FOR_FIELD.get(str(entry['loc'][0]), str(entry['loc'][0]))}: {entry['msg']}" for entry in error.errors()
    )


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

    import_models()

    try:
        await _seed_superuser(name, email, username, password)
    except ValidationError as error:
        raise SeedError(f"The admin settings don't describe a valid account: {_setting_failures(error)}") from error
    except (OSError, SQLAlchemyError) as error:
        raise SeedError(f"Could not seed the superuser: {type(error).__name__}") from error


async def _seed_superuser(name: str, email: str, username: str, password: str) -> None:
    """Write the superuser row, or report what stopped it."""
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
                f"ADMIN_EMAIL already belongs to user {existing['username']}, who is not a superuser. "
                "Choose another ADMIN_EMAIL, or promote that account deliberately."
            )

        try:
            created = await user_service.create(
                UserCreate(name=name, email=email, username=username, password=password), session
            )
        except PasswordPolicyException as error:
            raise SeedError(f"ADMIN_PASSWORD doesn't meet the password policy: {_policy_failures(error)}") from error
        except DomainError as error:
            raise SeedError(f"Could not seed the superuser: {error}") from error

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
