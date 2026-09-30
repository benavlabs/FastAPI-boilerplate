import asyncio
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from src.infrastructure.config.base import ini_value
from src.infrastructure.config.settings import EnvironmentOption, settings
from src.infrastructure.database.registry import import_models
from src.infrastructure.database.session import Base
from src.infrastructure.security.production_validator import is_weak_secret_key

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config


# Production safety checks
def validate_production_migration():
    """Refuse to migrate production unless the caller said so deliberately.

    The environment comes from settings rather than the process environment, so a
    production ``.env`` still trips the gate.
    """
    if settings.ENVIRONMENT == EnvironmentOption.PRODUCTION:
        print("🚨 PRODUCTION MIGRATION DETECTED")

        # Require explicit confirmation
        confirm = os.getenv("CONFIRM_PRODUCTION_MIGRATION")
        if confirm != "yes":
            raise Exception(
                "Production migration requires CONFIRM_PRODUCTION_MIGRATION=yes environment variable. "
                "This ensures you understand you're migrating production data."
            )

        if is_weak_secret_key(settings.SECRET_KEY):
            raise Exception("SECRET_KEY is missing, a placeholder, or too weak to migrate production with.")

        # Warn about production migration
        print("✅ Production migration confirmed")
        print("🔄 Running migration against production database...")
        print("⚠️  This operation will modify production data!")


config.set_main_option("sqlalchemy.url", ini_value(settings.DATABASE_URL))

validate_production_migration()

if config.config_file_name is not None:
    fileConfig(config.config_file_name)


# Import all models to ensure they're registered with SQLAlchemy
import_models()
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
