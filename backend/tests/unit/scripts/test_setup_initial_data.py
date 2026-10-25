"""What the seeding script does about the schema, in a project where alembic owns it.

Creating tables here would write them behind alembic's back, and a baseline applied to
that database then fails on the first table that already exists
(``DuplicateTableError: relation "roles" already exists``).
"""

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import create_async_engine

from tests.unit.scripts.seed_helpers import run_script, script_environment

pytestmark = pytest.mark.asyncio

FRESH_DATABASE = "setup_initial_data_fresh"


@pytest.fixture
async def an_empty_database(test_db_url: str):
    """A database of its own with nothing in it, dropped again afterwards."""
    administrative = create_async_engine(test_db_url, isolation_level="AUTOCOMMIT")
    async with administrative.connect() as connection:
        await connection.execute(text(f'DROP DATABASE IF EXISTS "{FRESH_DATABASE}"'))
        await connection.execute(text(f'CREATE DATABASE "{FRESH_DATABASE}"'))

    yield test_db_url.rsplit("/", 1)[0] + f"/{FRESH_DATABASE}"

    async with administrative.connect() as connection:
        await connection.execute(text(f'DROP DATABASE IF EXISTS "{FRESH_DATABASE}"'))
    await administrative.dispose()


ADMIN = {
    "ADMIN_NAME": "Admin User",
    "ADMIN_EMAIL": "admin@example.com",
    "ADMIN_USERNAME": "seededadmin",
    "ADMIN_PASSWORD": "Str0ngAdmin!",
}


def _seed(url: str, **extra: str):
    """Run the script as an operator does, with the superuser settings a seeder needs.

    The drill's copy of the project carries no ``.env``, so anything the script reads has
    to be in the environment it is handed.
    """
    return run_script("setup_initial_data", script_environment(url, **ADMIN, **extra))


async def _tables_in(url: str) -> list[str]:
    engine = create_async_engine(url)
    try:
        async with engine.connect() as connection:
            return await connection.run_sync(lambda sync: inspect(sync).get_table_names())
    finally:
        await engine.dispose()


async def test_the_script_creates_no_tables_where_alembic_owns_the_schema(an_empty_database: str):
    """Off is its default outside local and development, which is where migrations run."""
    completed = _seed(an_empty_database, CREATE_TABLES_ON_STARTUP="false")

    assert await _tables_in(an_empty_database) == []
    assert "creating no tables" in completed.stdout + completed.stderr


async def test_the_script_says_to_migrate_rather_than_failing_in_a_seeder(an_empty_database: str):
    """A seeder reaching for a table that isn't there reports the table, not the missing schema."""
    completed = _seed(an_empty_database, CREATE_TABLES_ON_STARTUP="false")

    assert completed.returncode != 0
    reported = completed.stdout + completed.stderr
    assert "Not seeding" in reported
    assert "alembic upgrade head" in reported
    assert "Running create_first_superuser" not in reported


async def test_the_script_creates_them_where_the_project_does(an_empty_database: str):
    completed = _seed(an_empty_database, CREATE_TABLES_ON_STARTUP="true")

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "user" in await _tables_in(an_empty_database)
