import asyncio
import importlib
import os
import pkgutil
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from src.infrastructure.config.settings import settings
from src.infrastructure.database.session import Base

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config


# Production safety checks
def validate_production_migration():
    """Validate production migration safety."""
    environment = os.getenv("ENVIRONMENT", "development")

    if environment == "production":
        print("🚨 PRODUCTION MIGRATION DETECTED")

        # Require explicit confirmation
        confirm = os.getenv("CONFIRM_PRODUCTION_MIGRATION")
        if confirm != "yes":
            raise Exception(
                "Production migration requires CONFIRM_PRODUCTION_MIGRATION=yes environment variable. "
                "This ensures you understand you're migrating production data."
            )

        # Check for required production environment variables
        required_vars = ["DATABASE_URL", "SECRET_KEY"]
        missing_vars = [var for var in required_vars if not os.getenv(var)]
        if missing_vars:
            raise Exception(f"Missing required production environment variables: {missing_vars}")

        # Warn about production migration
        print("✅ Production migration confirmed")
        print("🔄 Running migration against production database...")
        print("⚠️  This operation will modify production data!")


# Build the database URL from settings - use the built-in DATABASE_URL property
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

# Run production safety checks
validate_production_migration()

if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def import_models(package_name):
    """Automatically import all models from a package and its subpackages."""
    package = importlib.import_module(package_name)
    for _, module_name, _ in pkgutil.walk_packages(package.__path__, package.__name__ + "."):
        importlib.import_module(module_name)


# Import all models to ensure they're registered with SQLAlchemy
import_models("src.modules")
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL and not an Engine, though an Engine is acceptable here as well.  By
    skipping the Engine creation we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the script output.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """In this scenario we need to create an Engine and associate a connection with the context."""

    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""

    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
