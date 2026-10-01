"""Tests for the Tier admin view configuration."""

from typing import cast

import pytest
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.tier.admin import TierAdmin
from src.modules.tier.crud import crud_tiers
from src.modules.tier.schemas import TierCreate
from tests.unit.interfaces.admin.helpers import exported_rows

pytestmark = pytest.mark.asyncio


def _no_request() -> Request:
    """The listing query reads nothing off the request."""
    return cast(Request, None)


async def test_tier_admin_form_does_not_include_users():
    """The tier form must not preload a tier's users or list every user as an option."""
    assert "users" not in TierAdmin().get_form_columns()


async def test_tier_admin_details_do_not_include_users():
    """The tier details page must not preload every user assigned to the tier."""
    assert "users" not in TierAdmin().get_details_columns()


async def test_the_listing_leaves_out_deleted_tiers(db_session: AsyncSession, test_tier: dict):
    """The panel's listing leaves out a tier a soft delete has taken out."""
    await crud_tiers.delete(db=db_session, name=test_tier["name"])

    listed = await db_session.execute(TierAdmin().list_query(_no_request()))

    assert [row.name for row in listed.scalars().all()] == []


async def test_a_live_tier_is_listed(db_session: AsyncSession, test_tier: dict):
    listed = await db_session.execute(TierAdmin().list_query(_no_request()))

    assert test_tier["name"] in [row.name for row in listed.scalars().all()]


async def test_the_csv_export_writes_a_formula_like_tier_name_as_text(db_session: AsyncSession):
    """The tier's name and description reach the file as text."""
    await crud_tiers.create(db=db_session, object=TierCreate(name="@SUM(1+1)", description="+2"))
    tiers = (await db_session.execute(TierAdmin().list_query(_no_request()))).scalars().all()

    header, *rows = await exported_rows(TierAdmin(), list(tiers))
    exported = [row[header.index("name")] for row in rows]

    assert "'@SUM(1+1)" in exported
    assert rows[exported.index("'@SUM(1+1)")][header.index("description")] == "'+2"
