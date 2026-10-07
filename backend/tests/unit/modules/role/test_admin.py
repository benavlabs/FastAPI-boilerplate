"""Tests for the RBAC admin views: roles, their grants, and who holds them."""

from types import SimpleNamespace
from typing import cast

import pytest
from fastapi import Request
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.infrastructure.permissions import all_permissions
from src.modules.role.admin import RoleAdmin, RolePermissionAdmin, UserRoleAdmin
from src.modules.role.models import Role, RolePermission, UserRole
from src.modules.user.models import User
from src.wiring.admin import ADMIN_VIEWS

pytestmark = pytest.mark.asyncio


def _no_request() -> Request:
    """The listing query reads nothing off the request."""
    return cast(Request, None)


async def _stored_role(db_session: AsyncSession) -> Role:
    role = Role(name="editor", description="Edits things")
    db_session.add(role)
    await db_session.commit()

    return role


async def test_the_three_rbac_views_are_registered():
    assert {RoleAdmin, RolePermissionAdmin, UserRoleAdmin} <= set(ADMIN_VIEWS)


async def test_a_roles_permissions_read_as_one_cell():
    """The listing shows the names a role carries, not the repr of its grant rows."""
    role = SimpleNamespace(
        permissions=[
            SimpleNamespace(permission_name="user.update"),
            SimpleNamespace(permission_name="role.read"),
        ]
    )

    _, listed = await RoleAdmin().get_list_value(role, "permissions")
    _, detailed = await RoleAdmin().get_detail_value(role, "permissions")

    assert listed == "role.read, user.update"
    assert detailed == listed


async def test_the_role_form_leaves_the_grants_and_holders_out():
    """Editing a role's name must not offer every grant row and every holder as options."""
    columns = RoleAdmin().get_form_columns()

    assert "permissions" not in columns
    assert "user_roles" not in columns


async def test_the_role_details_do_not_preload_every_holder():
    assert "user_roles" not in RoleAdmin().get_details_columns()


class TestTheGrantForm:
    """The permission picker, through sqladmin's own form path."""

    @pytest.fixture
    def grant_view(self, db_session: AsyncSession, monkeypatch) -> RolePermissionAdmin:
        maker = async_sessionmaker(bind=db_session.bind, class_=AsyncSession, expire_on_commit=False)
        monkeypatch.setattr(RolePermissionAdmin, "session_maker", maker, raising=False)

        return RolePermissionAdmin()

    async def test_it_offers_every_registered_permission_and_nothing_else(self, grant_view: RolePermissionAdmin):
        form = await grant_view.scaffold_form()

        assert {value for value, _ in form().permission_name.choices} == set(all_permissions())

    async def test_a_name_the_registry_does_not_know_fails_validation(self, grant_view: RolePermissionAdmin):
        form_class = await grant_view.scaffold_form()
        form = form_class(formdata=None, data={"permission_name": "widget.explode"})

        assert not form.validate()
        assert "permission_name" in form.errors

    async def test_the_panel_writes_a_grant(self, grant_view: RolePermissionAdmin, db_session: AsyncSession):
        role = await _stored_role(db_session)

        await grant_view.insert_model(_no_request(), {"role": str(role.id), "permission_name": "role.read"})

        stored = await db_session.execute(select(RolePermission).where(RolePermission.role_id == role.id))
        assert [grant.permission_name for grant in stored.scalars().all()] == ["role.read"]


async def test_a_grant_the_registry_does_not_know_is_refused(db_session: AsyncSession):
    """A write that goes around the form is refused by the model too."""
    role = await _stored_role(db_session)

    with pytest.raises(ValueError, match="widget.explode"):
        RolePermission(role_id=role.id, permission_name="widget.explode")


async def _listing_and_count(db_session: AsyncSession) -> tuple[list[tuple[int, int]], int]:
    """What the panel's holder page shows, and the total it paginates by."""
    view = UserRoleAdmin()
    listed = await db_session.execute(view.list_query(_no_request()))
    counted = await db_session.execute(view.count_query(_no_request()))

    return [(row.user_id, row.role_id) for row in listed.scalars().all()], counted.scalar_one()


async def test_the_holder_listing_leaves_out_deleted_accounts(db_session: AsyncSession, test_user: dict):
    """An account a soft delete has taken out is not somebody the panel assigns roles to."""
    role = await _stored_role(db_session)
    db_session.add(UserRole(user_id=test_user["id"], role_id=role.id))
    await db_session.commit()

    assert await _listing_and_count(db_session) == ([(test_user["id"], role.id)], 1)

    await db_session.execute(update(User).where(User.id == test_user["id"]).values(is_deleted=True))
    await db_session.commit()

    assert await _listing_and_count(db_session) == ([], 0)


async def test_the_holder_form_does_not_offer_a_deleted_account(
    db_session: AsyncSession, test_user: dict, test_user_2: dict, monkeypatch
):
    """A role handed to an account the panel's own listing hides would be invisible there."""
    maker = async_sessionmaker(bind=db_session.bind, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr(UserRoleAdmin, "session_maker", maker, raising=False)
    await db_session.execute(update(User).where(User.id == test_user["id"]).values(is_deleted=True))
    await db_session.commit()

    form = await UserRoleAdmin().scaffold_form()
    offered = [str(value) for value, _ in form().user._select_data]

    assert str(test_user_2["id"]) in offered
    assert str(test_user["id"]) not in offered
