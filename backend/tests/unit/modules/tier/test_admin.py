"""Tests for the Tier admin view configuration."""

from typing import cast

import pytest
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.modules.tier.admin import TierAdmin
from src.modules.tier.crud import crud_tiers
from src.modules.tier.schemas import TierCreate
from src.modules.user.admin import UserAdmin
from src.modules.user.models import User
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


class TestThePanelPuttingAUserOnATier:
    """The tier picker and the save, through sqladmin's own form path."""

    @pytest.fixture
    def user_view(self, db_session: AsyncSession, monkeypatch) -> UserAdmin:
        maker = async_sessionmaker(bind=db_session.bind, class_=AsyncSession, expire_on_commit=False)
        monkeypatch.setattr(UserAdmin, "session_maker", maker, raising=False)

        return UserAdmin()

    async def test_the_tier_field_renders_on_both_forms(self, user_view: UserAdmin):
        """The form rule names the ``tier`` relationship, which sqladmin scaffolds into a field."""
        create_fields = (await user_view.scaffold_form(user_view.form_create_rules))()._fields
        edit_fields = (await user_view.scaffold_form(user_view.form_edit_rules))()._fields

        assert "tier" in create_fields
        assert "tier" in edit_fields

    async def _choices(self, view: UserAdmin) -> list[str]:
        form = await view.scaffold_form(view.form_edit_rules)

        return [str(value) for value, _ in form().tier._select_data]

    async def test_a_deleted_tier_is_refused(
        self, user_view: UserAdmin, db_session: AsyncSession, test_user: dict, test_tier: dict
    ):
        await crud_tiers.delete(db=db_session, name=test_tier["name"])

        with pytest.raises(ValueError, match="deleted"):
            await user_view.update_model(_no_request(), str(test_user["id"]), {"tier": str(test_tier["id"])})

        stored = await db_session.get_one(User, test_user["id"])
        await db_session.refresh(stored)
        assert stored.tier_id is None

    async def test_a_live_tier_is_saved(self, user_view: UserAdmin, db_session: AsyncSession, test_user: dict, test_tier: dict):
        await user_view.update_model(_no_request(), str(test_user["id"]), {"tier": str(test_tier["id"])})

        stored = await db_session.get_one(User, test_user["id"])
        await db_session.refresh(stored)
        assert stored.tier_id == test_tier["id"]

    async def test_the_picker_leaves_out_a_deleted_tier(
        self, user_view: UserAdmin, db_session: AsyncSession, test_tier: dict, second_test_tier: dict
    ):
        await crud_tiers.delete(db=db_session, name=test_tier["name"])

        choices = await self._choices(user_view)

        assert str(second_test_tier["id"]) in choices
        assert str(test_tier["id"]) not in choices


async def test_the_count_matches_the_listing(db_session: AsyncSession, test_tier: dict, second_test_tier: dict):
    """Pagination counts the rows the listing shows."""
    await crud_tiers.delete(db=db_session, name=test_tier["name"])
    view = TierAdmin()

    listed = (await db_session.execute(view.list_query(_no_request()))).scalars().all()
    counted = (await db_session.execute(view.count_query(_no_request()))).scalar_one()

    assert len(listed) == 1
    assert counted == 1
