"""The authorization interface: how the sources a project wired become a verdict.

These tests contribute their own sources, so they hold whatever a project happens
to have selected: the interface must behave the same with one source, with
several, and with none at all.
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.auth.authorization import load_permissions, require_permissions
from src.infrastructure.permissions import all_permissions


def _source(*names: str):
    async def source(db: AsyncSession, user_id: int) -> frozenset[str]:
        return frozenset(names)

    return source


async def test_a_superuser_holds_everything_registered_without_asking_a_source(db_session: AsyncSession):
    async def explode(db: AsyncSession, user_id: int) -> frozenset[str]:
        raise AssertionError("a superuser needs no lookup")

    permissions = await load_permissions(db_session, 999999, is_superuser=True, sources=(explode,))

    assert permissions == all_permissions()


async def test_the_holder_gets_the_union_of_every_source(db_session: AsyncSession):
    sources = (_source("user.read"), _source("tier.read", "user.read"))

    assert await load_permissions(db_session, 1, sources=sources) == {"user.read", "tier.read"}


async def test_without_a_source_a_non_superuser_holds_nothing(db_session: AsyncSession):
    """A project that selected no role feature falls back to superuser-only checks."""
    assert await load_permissions(db_session, 1, sources=()) == frozenset()


async def test_a_name_no_longer_registered_grants_nothing(db_session: AsyncSession):
    """Whatever a source answers, only registered permissions count."""
    permissions = await load_permissions(db_session, 1, sources=(_source("user.read", "user.retired"),))

    assert permissions == {"user.read"}


def test_require_permissions_rejects_unknown_permission():
    with pytest.raises(ValueError, match="Unknown permission name"):
        require_permissions("user.reed")
