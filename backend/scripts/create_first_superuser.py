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
from src.modules.common.exceptions import UserNotFoundError  # noqa: E402
from src.modules.user.models import User  # noqa: E402
from src.modules.user.schemas import UserCreate  # noqa: E402
from src.modules.user.service import UserService  # noqa: E402

logger = get_logger()


async def create_first_superuser() -> None:
    """
    Create the first superuser in the database if it doesn't exist.

    This script uses environment variables for configuration:
    - ADMIN_NAME: The admin's full name
    - ADMIN_EMAIL: The admin's email address
    - ADMIN_USERNAME: The admin's username
    - ADMIN_PASSWORD: The admin's password
    """
    try:
        name = settings.ADMIN_NAME
        email = settings.ADMIN_EMAIL
        username = settings.ADMIN_USERNAME
        password = settings.ADMIN_PASSWORD

        if not all([name, email, username, password]):
            logger.error("Admin configuration is incomplete. Please check environment variables.")
            logger.info("Using default admin credentials for testing")
            name = "Admin User"
            email = "admin@example.com"
            username = "admin"
            password = "adminpassword"

        async with local_session() as session:
            user_service = UserService()

            user = None
            try:
                user_model = await user_service.get_by_email(email, session)
                if user_model:
                    logger.info(f"Superuser with email {email} already exists.")
                    if not user_model["is_superuser"]:
                        user_model["is_superuser"] = True
                        await session.commit()
                        logger.info(f"Updated user {username} to be a superuser")
                    return
            except UserNotFoundError:
                logger.info(f"No user found with email {email}, creating a new superuser")

            user_data = UserCreate(name=name, email=email, username=username, password=password)

            user = await user_service.create(user_data, session)

            if hasattr(user, "id"):
                user_id = user.id
            else:
                user_id = user["id"]

            stmt = update(User).where(User.id == user_id).values(is_superuser=True)
            await session.execute(stmt)
            await session.commit()

            logger.info(f"Superuser {username} created successfully with ID {user_id}")

    except Exception as e:
        logger.error(f"Error creating superuser: {e}")


async def main() -> None:
    try:
        await create_first_superuser()
    finally:
        await close_database()


if __name__ == "__main__":
    asyncio.run(main())
