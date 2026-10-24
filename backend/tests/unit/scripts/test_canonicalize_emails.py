"""Bringing the addresses an older deployment stored into the canonical form."""

import pytest
from sqlalchemy import inspect, text

from src.infrastructure.database.session import build_engine
from tests.unit.scripts.seed_helpers import run_script, script_environment

INDEX = "ix_user_email_lower"

STORED = """
INSERT INTO "user" (name, username, email, hashed_password, profile_image_url,
                    is_superuser, email_verified, is_deleted, created_at)
VALUES (:name, :username, :email, 'hashed', 'https://profileimageurl.com', false, false, false, now())
"""


async def _database_from_before_the_index(url: str, *rows: tuple[str, str]) -> None:
    """The tables without the index, holding ``rows`` as an older version stored them."""
    engine = build_engine(url)
    async with engine.begin() as connection:
        await connection.execute(text(f"DROP INDEX IF EXISTS {INDEX}"))
        await connection.execute(text('DELETE FROM "user"'))
        for username, email in rows:
            await connection.execute(text(STORED), {"name": username.title(), "username": username, "email": email})
    await engine.dispose()


async def _stored_addresses(url: str) -> list[str]:
    engine = build_engine(url)
    async with engine.connect() as connection:
        addresses = list((await connection.execute(text('SELECT email FROM "user" ORDER BY username'))).scalars())
    await engine.dispose()

    return addresses


async def _indexes(url: str) -> list[str]:
    engine = build_engine(url)
    async with engine.connect() as connection:
        names = await connection.run_sync(lambda sync: [str(index["name"]) for index in inspect(sync).get_indexes("user")])
    await engine.dispose()

    return names


@pytest.mark.asyncio
async def test_it_canonicalizes_what_was_stored_and_adds_the_index(test_db_url: str, test_db_engine):
    await _database_from_before_the_index(test_db_url, ("owner", "\tOwner@Example.COM\n"), ("other", " other@example.com "))

    completed = run_script("canonicalize_emails", script_environment(test_db_url))

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert await _stored_addresses(test_db_url) == ["other@example.com", "owner@example.com"]
    assert INDEX in await _indexes(test_db_url)


@pytest.mark.asyncio
async def test_a_second_run_changes_nothing(test_db_url: str, test_db_engine):
    await _database_from_before_the_index(test_db_url, ("owner", "Owner@Example.com"))
    assert run_script("canonicalize_emails", script_environment(test_db_url)).returncode == 0

    completed = run_script("canonicalize_emails", script_environment(test_db_url))

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert await _stored_addresses(test_db_url) == ["owner@example.com"]
    assert INDEX in await _indexes(test_db_url)


@pytest.mark.asyncio
@pytest.mark.parametrize("second", ["OWNER@example.com", "owner@example.com\t", "\nowner@example.com"])
async def test_it_refuses_while_two_accounts_hold_one_address(test_db_url: str, test_db_engine, second: str):
    """Choosing which account keeps the address is a decision for a person.

    The whitespace cases are the ones the app itself would strip: it canonicalises with
    Python's ``strip()``, which takes tabs and newlines as well as spaces.
    """
    await _database_from_before_the_index(test_db_url, ("owner", "owner@example.com"), ("other", second))

    completed = run_script("canonicalize_emails", script_environment(test_db_url))
    printed = completed.stdout + completed.stderr

    assert completed.returncode == 1
    assert "owner@example.com" in printed
    assert await _stored_addresses(test_db_url) == [second, "owner@example.com"]
    assert INDEX not in await _indexes(test_db_url)
