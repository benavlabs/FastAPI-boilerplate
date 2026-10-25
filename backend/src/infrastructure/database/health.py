"""Whether the database is reachable, and whether it holds the schema the app needs."""

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text
from sqlalchemy.exc import ProgrammingError

from ..composition import ReadinessCheck
from ..config.settings import settings
from .registry import import_models
from .session import Base, async_session

ALEMBIC_INI = Path(__file__).resolve().parents[3] / "alembic.ini"
"""The project's alembic configuration, beside ``src`` in the repository and in the image."""


async def database_is_reachable() -> None:
    """Raise unless a trivial statement comes back from the database."""
    async for session in async_session():
        await session.execute(text("SELECT 1"))


def expected_heads() -> set[str]:
    """The revisions the code carries, or nothing where it carries no migrations at all.

    Read through alembic's own configuration, whose ``script_location`` is relative to the
    ini file, so the answer doesn't depend on the working directory the app was started in.
    """
    if not ALEMBIC_INI.exists():
        return set()

    return set(ScriptDirectory.from_config(Config(str(ALEMBIC_INI))).get_heads())


async def every_declared_table_exists() -> None:
    """Raise unless the database holds every table the models declare.

    An unmigrated database answers ``SELECT 1`` and then fails every request that reads a
    row, so reachability alone reports a deploy that never ran its migrations as ready.

    Raises:
        RuntimeError: The database is missing a table the models declare.
    """
    import_models()
    declared = set(Base.metadata.tables)

    async for session in async_session():
        connection = await session.connection()
        present = set(await connection.run_sync(lambda sync: inspect(sync).get_table_names()))

    missing = sorted(declared - present)
    if missing:
        raise RuntimeError(f"the database is missing {len(missing)} table(s) the models declare: {', '.join(missing)}")


async def the_schema_is_current() -> None:
    """Raise unless the database carries the schema this code was written against.

    Where the project has migrations, that means the database is at their head: a table
    check alone passes a database that has every table and is missing a column, which is
    what an unapplied migration leaves behind. Where it has none, or where the app creates
    its own tables on startup, the tables themselves are all there is to compare.

    Raises:
        RuntimeError: The database is at a different revision, or was never migrated, or
            is missing a table the models declare.
    """
    heads = expected_heads()
    if not heads or settings.CREATE_TABLES_ON_STARTUP:
        await every_declared_table_exists()
        return

    async for session in async_session():
        try:
            stamped = await session.execute(text("SELECT version_num FROM alembic_version"))
        except ProgrammingError as error:
            raise RuntimeError(
                f"the database has no alembic_version table, so it was never migrated; "
                f"the code expects {', '.join(sorted(heads))}"
            ) from error

        applied = set(stamped.scalars())

    if applied != heads:
        raise RuntimeError(
            f"the database is at {', '.join(sorted(applied)) or 'no revision'}, the code expects {', '.join(sorted(heads))}"
        )


readiness = ReadinessCheck("database", database_is_reachable, target=lambda: settings.DATABASE_URL)
schema_readiness = ReadinessCheck("schema", the_schema_is_current)
"""Named with no target, so it is asked rather than mirrored from the reachability check."""
