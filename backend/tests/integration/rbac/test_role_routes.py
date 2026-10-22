"""Managing roles through the API: who may, and what the delegation checks refuse.

Callers sign in for real, so the permission lookup and the escalation checks run against
the same session the routes use.
"""

import asyncio
from datetime import UTC, datetime
from typing import Any

import pytest
from crudauth import Principal
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.infrastructure.auth import authorization as authz
from src.interfaces.main import app
from src.modules.role import service as role_service
from src.modules.role.exceptions import RoleExistsError
from src.modules.role.models import Role, RolePermission, UserRole
from src.modules.role.service import RoleService
from src.modules.user.models import User
from tests.integration.rbac.test_user_permissions import _grant, _login


async def _never_taken() -> bool:
    """A name the pre-check reports as free, whatever the table holds."""
    return False


pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("fresh_login_lockout")]

MANAGING = ("role.read", "role.create", "role.update", "role.delete", "role.assign")


async def _carried(db: AsyncSession, role_id: int) -> list[str]:
    rows = await db.execute(select(RolePermission.permission_name).where(RolePermission.role_id == role_id))

    return sorted(rows.scalars().all())


async def _role_named(db: AsyncSession, name: str) -> Role | None:
    return (await db.execute(select(Role).where(Role.name == name))).scalar_one_or_none()


async def _holders_of(db: AsyncSession, role_id: int) -> list[int]:
    held = await db.execute(select(UserRole.user_id).where(UserRole.role_id == role_id).order_by(UserRole.user_id))

    return list(held.scalars().all())


async def _holds(db: AsyncSession, user_id: int, role_id: int) -> bool:
    held = await db.execute(select(UserRole).where(UserRole.user_id == user_id, UserRole.role_id == role_id))

    return held.scalar_one_or_none() is not None


@pytest.fixture
async def manager(client: AsyncClient, db_session: AsyncSession, test_user: dict) -> dict[str, Any]:
    """A caller holding every role.* permission, plus user.read to delegate."""
    await _grant(db_session, test_user["id"], "role-manager", *MANAGING, "user.read")
    csrf = await _login(client, test_user)

    return {"user": test_user, "csrf": csrf}


class TestListingAndReading:
    """``role.read`` opens both; without it the routes answer 403."""

    async def test_a_holder_lists_roles_with_what_they_carry(
        self, client: AsyncClient, db_session: AsyncSession, manager: dict[str, Any]
    ):
        response = await client.get("/api/v1/roles/", headers={"X-CSRF-Token": manager["csrf"]})

        assert response.status_code == 200
        listed = response.json()["data"]
        assert [role["name"] for role in listed] == ["role-manager"]
        assert listed[0]["permissions"] == sorted([*MANAGING, "user.read"])

    async def test_a_holder_reads_one_role(self, client: AsyncClient, db_session: AsyncSession, manager: dict[str, Any]):
        role = await _role_named(db_session, "role-manager")
        assert role is not None

        response = await client.get(f"/api/v1/roles/{role.id}", headers={"X-CSRF-Token": manager["csrf"]})

        assert response.status_code == 200
        assert response.json()["name"] == "role-manager"

    async def test_a_role_that_does_not_exist_is_a_404(self, client: AsyncClient, manager: dict[str, Any]):
        assert (await client.get("/api/v1/roles/9999")).status_code == 404

    async def test_without_the_permission_the_listing_is_refused(
        self, client: AsyncClient, db_session: AsyncSession, test_user: dict
    ):
        await _login(client, test_user)

        assert (await client.get("/api/v1/roles/")).status_code == 403

    async def test_without_a_session_the_listing_is_refused(self, client: AsyncClient):
        assert (await client.get("/api/v1/roles/")).status_code == 401


class TestCreating:
    """A role may only be created carrying permissions the caller holds."""

    async def test_a_holder_creates_a_role(self, client: AsyncClient, db_session: AsyncSession, manager: dict[str, Any]):
        response = await client.post(
            "/api/v1/roles/",
            json={"name": "editor", "description": "Edits profiles", "permissions": ["user.read"]},
            headers={"X-CSRF-Token": manager["csrf"]},
        )

        assert response.status_code == 201
        assert response.json()["permissions"] == ["user.read"]
        created = await _role_named(db_session, "editor")
        assert created is not None
        assert await _carried(db_session, created.id) == ["user.read"]

    async def test_a_name_carrying_a_nul_is_refused(self, client: AsyncClient, manager: dict[str, Any]):
        """A NUL encodes, and Postgres then refuses the whole statement carrying it."""
        response = await client.post(
            "/api/v1/roles/",
            json={"name": "a\u0000b", "permissions": []},
            headers={"X-CSRF-Token": manager["csrf"]},
        )

        assert response.status_code == 422

    async def test_a_name_already_taken_is_a_conflict(self, client: AsyncClient, manager: dict[str, Any]):
        response = await client.post(
            "/api/v1/roles/",
            json={"name": "role-manager", "permissions": []},
            headers={"X-CSRF-Token": manager["csrf"]},
        )

        assert response.status_code == 409

    async def test_a_permission_the_registry_does_not_know_is_refused(
        self, client: AsyncClient, db_session: AsyncSession, manager: dict[str, Any]
    ):
        """Nothing would ever check it, and the refusal doesn't echo what was sent."""
        response = await client.post(
            "/api/v1/roles/",
            json={"name": "editor", "permissions": ["user.read", "widget.explode"]},
            headers={"X-CSRF-Token": manager["csrf"]},
        )

        assert response.status_code == 422
        assert "widget.explode" not in response.text
        assert await _role_named(db_session, "editor") is None

    async def test_granting_what_the_caller_does_not_hold_is_refused(
        self, client: AsyncClient, db_session: AsyncSession, manager: dict[str, Any]
    ):
        """The escalation this check exists for: a role is a way to hand yourself more."""
        response = await client.post(
            "/api/v1/roles/",
            json={"name": "stronger", "permissions": ["user.delete"]},
            headers={"X-CSRF-Token": manager["csrf"]},
        )

        assert response.status_code == 403
        assert await _role_named(db_session, "stronger") is None

    async def test_a_superuser_grants_anything(self, client: AsyncClient, db_session: AsyncSession, test_superuser: dict):
        csrf = await _login(client, test_superuser)

        response = await client.post(
            "/api/v1/roles/",
            json={"name": "everything", "permissions": ["user.delete"]},
            headers={"X-CSRF-Token": csrf},
        )

        assert response.status_code == 201
        created = await _role_named(db_session, "everything")
        assert created is not None
        assert await _carried(db_session, created.id) == ["user.delete"]

    async def test_without_the_permission_creating_is_refused(
        self, client: AsyncClient, db_session: AsyncSession, test_user: dict
    ):
        await _grant(db_session, test_user["id"], "reader", "role.read")
        csrf = await _login(client, test_user)

        response = await client.post(
            "/api/v1/roles/", json={"name": "editor", "permissions": []}, headers={"X-CSRF-Token": csrf}
        )

        assert response.status_code == 403
        assert await _role_named(db_session, "editor") is None


class TestRenaming:
    """``role.update`` changes the name and description; the permissions have their own route."""

    async def test_a_holder_renames_a_role(self, client: AsyncClient, db_session: AsyncSession, manager: dict[str, Any]):
        role = await _grant(db_session, manager["user"]["id"], "editor", "user.read")

        response = await client.patch(
            f"/api/v1/roles/{role.id}",
            json={"name": "senior-editor", "description": "Now with a better title"},
            headers={"X-CSRF-Token": manager["csrf"]},
        )

        assert response.status_code == 200
        assert response.json()["name"] == "senior-editor"
        assert await _role_named(db_session, "editor") is None

    async def test_a_name_another_role_holds_is_a_conflict(
        self, client: AsyncClient, db_session: AsyncSession, manager: dict[str, Any]
    ):
        role = await _grant(db_session, manager["user"]["id"], "editor", "user.read")

        response = await client.patch(
            f"/api/v1/roles/{role.id}", json={"name": "role-manager"}, headers={"X-CSRF-Token": manager["csrf"]}
        )

        assert response.status_code == 409

    async def test_relabelling_a_role_stronger_than_the_caller_is_refused(
        self, client: AsyncClient, db_session: AsyncSession, manager: dict[str, Any], test_user_2: dict
    ):
        """A role the caller could never have created must not be renamed into something else."""
        stronger = await _grant(db_session, test_user_2["id"], "admins", "user.delete")

        response = await client.patch(
            f"/api/v1/roles/{stronger.id}", json={"name": "harmless"}, headers={"X-CSRF-Token": manager["csrf"]}
        )

        assert response.status_code == 403
        assert await _role_named(db_session, "admins") is not None
        assert await _role_named(db_session, "harmless") is None

    async def test_a_name_another_request_took_first_is_a_conflict(
        self, db_session: AsyncSession, manager: dict[str, Any], monkeypatch
    ):
        """The pre-check can miss; the unique constraint is what finally decides."""
        service = RoleService()
        await _grant(db_session, manager["user"]["id"], "taken", "user.read")
        monkeypatch.setattr(RoleService, "_name_taken", staticmethod(lambda name, db: _never_taken()))
        principal = Principal(user_id=manager["user"]["id"], is_superuser=False)

        with pytest.raises(RoleExistsError):
            await service.create("taken", None, ["user.read"], principal, db_session, frozenset({"user.read"}))

        remaining = await db_session.execute(select(Role).where(Role.name == "taken"))
        assert len(remaining.scalars().all()) == 1

    async def test_the_permissions_cannot_be_changed_here(
        self, client: AsyncClient, db_session: AsyncSession, manager: dict[str, Any]
    ):
        role = await _grant(db_session, manager["user"]["id"], "editor", "user.read")

        response = await client.patch(
            f"/api/v1/roles/{role.id}",
            json={"permissions": ["user.delete"]},
            headers={"X-CSRF-Token": manager["csrf"]},
        )

        assert response.status_code == 422
        assert await _carried(db_session, role.id) == ["user.read"]


class TestSettingPermissions:
    """A caller may only hand out, or take away, permissions they hold themselves."""

    async def test_a_holder_replaces_what_a_role_carries(
        self, client: AsyncClient, db_session: AsyncSession, manager: dict[str, Any]
    ):
        role = await _grant(db_session, manager["user"]["id"], "editor", "user.read")

        response = await client.put(
            f"/api/v1/roles/{role.id}/permissions",
            json={"permissions": ["role.read"]},
            headers={"X-CSRF-Token": manager["csrf"]},
        )

        assert response.status_code == 200
        assert response.json()["permissions"] == ["role.read"]
        assert await _carried(db_session, role.id) == ["role.read"]

    async def test_adding_what_the_caller_does_not_hold_is_refused(
        self, client: AsyncClient, db_session: AsyncSession, manager: dict[str, Any]
    ):
        role = await _grant(db_session, manager["user"]["id"], "editor", "user.read")

        response = await client.put(
            f"/api/v1/roles/{role.id}/permissions",
            json={"permissions": ["user.read", "user.delete"]},
            headers={"X-CSRF-Token": manager["csrf"]},
        )

        assert response.status_code == 403
        assert await _carried(db_session, role.id) == ["user.read"]

    async def test_touching_a_role_stronger_than_the_caller_is_refused(
        self, client: AsyncClient, db_session: AsyncSession, manager: dict[str, Any], test_user_2: dict
    ):
        """Emptying a role you could never have created is the same escalation in reverse."""
        stronger = await _grant(db_session, test_user_2["id"], "admins", "user.delete")

        response = await client.put(
            f"/api/v1/roles/{stronger.id}/permissions",
            json={"permissions": []},
            headers={"X-CSRF-Token": manager["csrf"]},
        )

        assert response.status_code == 403
        assert await _carried(db_session, stronger.id) == ["user.delete"]

    async def test_a_permission_the_registry_does_not_know_is_refused(
        self, client: AsyncClient, db_session: AsyncSession, manager: dict[str, Any]
    ):
        role = await _grant(db_session, manager["user"]["id"], "editor", "user.read")

        response = await client.put(
            f"/api/v1/roles/{role.id}/permissions",
            json={"permissions": ["widget.explode"]},
            headers={"X-CSRF-Token": manager["csrf"]},
        )

        assert response.status_code == 422
        assert await _carried(db_session, role.id) == ["user.read"]


class TestDeleting:
    """``role.delete`` removes a role, under the same rule as creating one."""

    async def test_a_holder_deletes_a_role(self, client: AsyncClient, db_session: AsyncSession, manager: dict[str, Any]):
        role = await _grant(db_session, manager["user"]["id"], "editor", "user.read")

        response = await client.delete(f"/api/v1/roles/{role.id}", headers={"X-CSRF-Token": manager["csrf"]})

        assert response.status_code == 200
        assert await _role_named(db_session, "editor") is None
        assert not await _holds(db_session, manager["user"]["id"], role.id)

    async def test_deleting_a_role_stronger_than_the_caller_is_refused(
        self, client: AsyncClient, db_session: AsyncSession, manager: dict[str, Any], test_user_2: dict
    ):
        stronger = await _grant(db_session, test_user_2["id"], "admins", "user.delete")

        response = await client.delete(f"/api/v1/roles/{stronger.id}", headers={"X-CSRF-Token": manager["csrf"]})

        assert response.status_code == 403
        assert await _role_named(db_session, "admins") is not None

    async def test_without_the_permission_deleting_is_refused(
        self, client: AsyncClient, db_session: AsyncSession, test_user: dict
    ):
        role = await _grant(db_session, test_user["id"], "reader", "role.read")
        csrf = await _login(client, test_user)

        response = await client.delete(f"/api/v1/roles/{role.id}", headers={"X-CSRF-Token": csrf})

        assert response.status_code == 403
        assert await _role_named(db_session, "reader") is not None


class TestARoleCarryingAStaleName:
    """A stored name the registry no longer knows must not strand the role that carries it.

    Removing a feature takes its permissions out of the registry and leaves the grants
    behind, so every role that carried one would otherwise be unreachable.
    """

    STALE = "api_key.gone"

    async def _stranded(self, db: AsyncSession, user_id: int, name: str, *permissions: str) -> Role:
        """A role carrying ``permissions`` plus a grant nothing declares any more.

        The grant goes in as a statement: the model refuses an unregistered name, which is
        how one of these rows is left behind rather than written.
        """
        role = await _grant(db, user_id, name, *permissions)
        await db.execute(
            insert(RolePermission).values(role_id=role.id, permission_name=self.STALE, created_at=datetime.now(UTC))
        )
        await db.commit()

        return role

    async def test_a_superuser_renames_empties_and_deletes_it(
        self, client: AsyncClient, db_session: AsyncSession, test_superuser: dict
    ):
        renamed = await self._stranded(db_session, test_superuser["id"], "stranded", "user.read")
        emptied = await self._stranded(db_session, test_superuser["id"], "also-stranded", "user.read")
        csrf = await _login(client, test_superuser)

        answers = [
            (
                await client.patch(f"/api/v1/roles/{renamed.id}", json={"name": "rescued"}, headers={"X-CSRF-Token": csrf})
            ).status_code,
            (
                await client.put(
                    f"/api/v1/roles/{emptied.id}/permissions",
                    json={"permissions": ["user.read"]},
                    headers={"X-CSRF-Token": csrf},
                )
            ).status_code,
            (await client.delete(f"/api/v1/roles/{renamed.id}", headers={"X-CSRF-Token": csrf})).status_code,
        ]

        assert answers == [200, 200, 200]
        assert await _role_named(db_session, "rescued") is None
        assert await _carried(db_session, emptied.id) == ["user.read"]

    async def test_a_caller_holding_what_it_still_carries_edits_it(
        self, client: AsyncClient, db_session: AsyncSession, manager: dict[str, Any]
    ):
        """The stale name grants nothing, so holding it is not something to ask of the caller."""
        role = await self._stranded(db_session, manager["user"]["id"], "stranded", "user.read")

        renamed = await client.patch(
            f"/api/v1/roles/{role.id}", json={"name": "rescued"}, headers={"X-CSRF-Token": manager["csrf"]}
        )
        emptied = await client.put(
            f"/api/v1/roles/{role.id}/permissions", json={"permissions": []}, headers={"X-CSRF-Token": manager["csrf"]}
        )

        assert [renamed.status_code, emptied.status_code] == [200, 200]
        assert await _carried(db_session, role.id) == []

    async def test_a_put_drops_it(self, client: AsyncClient, db_session: AsyncSession, manager: dict[str, Any]):
        """Nothing else rewrites the row, so setting the permissions is how a stale name goes."""
        role = await self._stranded(db_session, manager["user"]["id"], "stranded", "user.read")

        response = await client.put(
            f"/api/v1/roles/{role.id}/permissions",
            json={"permissions": ["user.read"]},
            headers={"X-CSRF-Token": manager["csrf"]},
        )

        assert response.status_code == 200
        assert response.json()["permissions"] == ["user.read"]
        assert await _carried(db_session, role.id) == ["user.read"]

    async def test_a_caller_missing_a_registered_name_it_carries_is_still_refused(
        self, client: AsyncClient, db_session: AsyncSession, manager: dict[str, Any], test_user_2: dict
    ):
        """Ignoring the stale name must not let the rest of the role through."""
        role = await self._stranded(db_session, test_user_2["id"], "stranded", "user.delete")

        deleted = await client.delete(f"/api/v1/roles/{role.id}", headers={"X-CSRF-Token": manager["csrf"]})

        assert deleted.status_code == 403
        assert await _role_named(db_session, "stranded") is not None

    async def test_the_stale_name_cannot_be_asked_for_again(
        self, client: AsyncClient, db_session: AsyncSession, manager: dict[str, Any]
    ):
        """What the registry does not know is refused on the way in, stored or not."""
        role = await self._stranded(db_session, manager["user"]["id"], "stranded", "user.read")

        response = await client.put(
            f"/api/v1/roles/{role.id}/permissions",
            json={"permissions": [self.STALE]},
            headers={"X-CSRF-Token": manager["csrf"]},
        )

        assert response.status_code == 422
        assert sorted(await _carried(db_session, role.id)) == [self.STALE, "user.read"]


class TestAnAccountStrongerThanTheCaller:
    """Changing an account's roles is a way to take it over, so the account matters too."""

    async def test_unassigning_from_a_stronger_account_is_refused(
        self, client: AsyncClient, db_session: AsyncSession, manager: dict[str, Any], test_user_2: dict
    ):
        """The caller holds what this role carries, but not what the account holds besides it."""
        reachable = await _grant(db_session, test_user_2["id"], "editor", "user.read")
        await _grant(db_session, test_user_2["id"], "admins", "user.delete")

        response = await client.delete(
            f"/api/v1/roles/{reachable.id}/users/{test_user_2['id']}", headers={"X-CSRF-Token": manager["csrf"]}
        )

        assert response.status_code == 403
        assert await _holds(db_session, test_user_2["id"], reachable.id)

    async def test_assigning_to_a_superuser_is_refused(
        self, client: AsyncClient, db_session: AsyncSession, manager: dict[str, Any], test_superuser: dict
    ):
        role = await _grant(db_session, manager["user"]["id"], "editor", "user.read")

        response = await client.post(
            f"/api/v1/roles/{role.id}/users/{test_superuser['id']}", headers={"X-CSRF-Token": manager["csrf"]}
        )

        assert response.status_code == 403
        assert not await _holds(db_session, test_superuser["id"], role.id)

    async def test_unassigning_from_a_superuser_is_refused(
        self, client: AsyncClient, db_session: AsyncSession, manager: dict[str, Any], test_superuser: dict
    ):
        role = await _grant(db_session, test_superuser["id"], "editor", "user.read")

        response = await client.delete(
            f"/api/v1/roles/{role.id}/users/{test_superuser['id']}", headers={"X-CSRF-Token": manager["csrf"]}
        )

        assert response.status_code == 403
        assert await _holds(db_session, test_superuser["id"], role.id)

    async def test_deleting_a_role_a_stronger_account_holds_is_refused(
        self, client: AsyncClient, db_session: AsyncSession, manager: dict[str, Any], test_user_2: dict
    ):
        """Deleting the role takes the permission away from the account, reachable or not."""
        reachable = await _grant(db_session, test_user_2["id"], "editor", "user.read")
        await _grant(db_session, test_user_2["id"], "admins", "user.delete")

        response = await client.delete(f"/api/v1/roles/{reachable.id}", headers={"X-CSRF-Token": manager["csrf"]})

        assert response.status_code == 403
        assert await _role_named(db_session, "editor") is not None
        assert await _holds(db_session, test_user_2["id"], reachable.id)

    async def test_emptying_a_role_a_stronger_account_holds_is_refused(
        self, client: AsyncClient, db_session: AsyncSession, manager: dict[str, Any], test_user_2: dict
    ):
        reachable = await _grant(db_session, test_user_2["id"], "editor", "user.read")
        await _grant(db_session, test_user_2["id"], "admins", "user.delete")

        response = await client.put(
            f"/api/v1/roles/{reachable.id}/permissions",
            json={"permissions": []},
            headers={"X-CSRF-Token": manager["csrf"]},
        )

        assert response.status_code == 403
        assert await _carried(db_session, reachable.id) == ["user.read"]

    async def test_a_role_a_superuser_holds_is_refused_either_way(
        self, client: AsyncClient, db_session: AsyncSession, manager: dict[str, Any], test_superuser: dict
    ):
        """No scope expresses the flag, so an account carrying it is out of reach."""
        held = await _grant(db_session, test_superuser["id"], "editor", "user.read")

        emptied = await client.put(
            f"/api/v1/roles/{held.id}/permissions",
            json={"permissions": []},
            headers={"X-CSRF-Token": manager["csrf"]},
        )
        deleted = await client.delete(f"/api/v1/roles/{held.id}", headers={"X-CSRF-Token": manager["csrf"]})

        assert [emptied.status_code, deleted.status_code] == [403, 403]
        assert await _carried(db_session, held.id) == ["user.read"]
        assert await _role_named(db_session, "editor") is not None

    async def test_a_role_only_weaker_accounts_hold_is_deleted_and_emptied(
        self, client: AsyncClient, db_session: AsyncSession, manager: dict[str, Any], test_user_2: dict
    ):
        """The holder check only refuses what the caller could not reach account by account."""
        emptied = await _grant(db_session, test_user_2["id"], "editor", "user.read")
        deleted = await _grant(db_session, test_user_2["id"], "readers", "user.read")

        answers = [
            (
                await client.put(
                    f"/api/v1/roles/{emptied.id}/permissions",
                    json={"permissions": []},
                    headers={"X-CSRF-Token": manager["csrf"]},
                )
            ).status_code,
            (await client.delete(f"/api/v1/roles/{deleted.id}", headers={"X-CSRF-Token": manager["csrf"]})).status_code,
        ]

        assert answers == [200, 200]
        assert await _carried(db_session, emptied.id) == []
        assert await _role_named(db_session, "readers") is None

    async def test_one_holder_out_of_reach_refuses_the_whole_role(
        self, client: AsyncClient, db_session: AsyncSession, manager: dict[str, Any], test_user_2: dict, test_superuser: dict
    ):
        """Deleting it takes the role from every holder, so a reachable holder is not enough."""
        shared = await _grant(db_session, test_user_2["id"], "editor", "user.read")
        db_session.add(UserRole(user_id=test_superuser["id"], role_id=shared.id))
        await db_session.commit()

        response = await client.delete(f"/api/v1/roles/{shared.id}", headers={"X-CSRF-Token": manager["csrf"]})

        assert response.status_code == 403
        assert await _holds(db_session, test_user_2["id"], shared.id)

    async def test_a_holder_a_soft_delete_took_out_is_not_one(
        self, client: AsyncClient, db_session: AsyncSession, manager: dict[str, Any], test_user_2: dict
    ):
        """A deleted account's assignment rows stay behind, and its grants reach nobody."""
        emptied = await _grant(db_session, test_user_2["id"], "editor", "user.read")
        deleted = await _grant(db_session, test_user_2["id"], "readers", "user.read")
        await _grant(db_session, test_user_2["id"], "admins", "user.delete")
        await db_session.execute(update(User).where(User.id == test_user_2["id"]).values(is_deleted=True))
        await db_session.commit()

        answers = [
            (
                await client.put(
                    f"/api/v1/roles/{emptied.id}/permissions",
                    json={"permissions": []},
                    headers={"X-CSRF-Token": manager["csrf"]},
                )
            ).status_code,
            (await client.delete(f"/api/v1/roles/{deleted.id}", headers={"X-CSRF-Token": manager["csrf"]})).status_code,
        ]

        assert answers == [200, 200]
        assert await _carried(db_session, emptied.id) == []
        assert await _role_named(db_session, "readers") is None

    async def test_a_role_nobody_holds_is_deleted_and_emptied(
        self, client: AsyncClient, db_session: AsyncSession, manager: dict[str, Any]
    ):
        """Nothing is taken from anybody, so the holder check has nothing to refuse."""
        emptied = Role(name="unheld")
        deleted = Role(name="unheld-too")
        db_session.add_all([emptied, deleted])
        await db_session.flush()
        db_session.add(RolePermission(role_id=emptied.id, permission_name="user.read"))
        await db_session.commit()

        answers = [
            (
                await client.put(
                    f"/api/v1/roles/{emptied.id}/permissions",
                    json={"permissions": []},
                    headers={"X-CSRF-Token": manager["csrf"]},
                )
            ).status_code,
            (await client.delete(f"/api/v1/roles/{deleted.id}", headers={"X-CSRF-Token": manager["csrf"]})).status_code,
        ]

        assert answers == [200, 200]
        assert await _carried(db_session, emptied.id) == []
        assert await _role_named(db_session, "unheld-too") is None

    async def test_a_stronger_account_holding_another_role_reaches_nothing_here(
        self, client: AsyncClient, db_session: AsyncSession, manager: dict[str, Any], test_user_2: dict
    ):
        """Only the role's own holders are read, or one strong account would freeze every role."""
        reachable = await _grant(db_session, manager["user"]["id"], "editor", "user.read")
        await _grant(db_session, test_user_2["id"], "admins", "user.delete")

        response = await client.delete(f"/api/v1/roles/{reachable.id}", headers={"X-CSRF-Token": manager["csrf"]})

        assert response.status_code == 200
        assert await _role_named(db_session, "editor") is None

    @pytest.mark.parametrize("holder_is_a_superuser", [False, True])
    async def test_a_superuser_deletes_a_role_whoever_holds_it(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_superuser: dict,
        test_user_2: dict,
        holder_is_a_superuser: bool,
    ):
        """The holder check must not put a role beyond every caller, another superuser's included."""
        reachable = await _grant(db_session, test_user_2["id"], "editor", "user.read")
        await _grant(db_session, test_user_2["id"], "admins", "user.delete")
        if holder_is_a_superuser:
            await db_session.execute(update(User).where(User.id == test_user_2["id"]).values(is_superuser=True))
            await db_session.commit()
        csrf = await _login(client, test_superuser)

        response = await client.delete(f"/api/v1/roles/{reachable.id}", headers={"X-CSRF-Token": csrf})

        assert response.status_code == 200
        assert await _role_named(db_session, "editor") is None

    async def test_a_superuser_reaches_any_account(
        self, client: AsyncClient, db_session: AsyncSession, test_superuser: dict, test_user_2: dict
    ):
        reachable = await _grant(db_session, test_user_2["id"], "editor", "user.read")
        await _grant(db_session, test_user_2["id"], "admins", "user.delete")
        csrf = await _login(client, test_superuser)

        response = await client.delete(
            f"/api/v1/roles/{reachable.id}/users/{test_user_2['id']}", headers={"X-CSRF-Token": csrf}
        )

        assert response.status_code == 200
        assert not await _holds(db_session, test_user_2["id"], reachable.id)


class TestAssigning:
    """``role.assign`` hands a role out, and only one the caller could hold themselves."""

    async def test_a_holder_assigns_and_unassigns(
        self, client: AsyncClient, db_session: AsyncSession, manager: dict[str, Any], test_user_2: dict
    ):
        role = await _grant(db_session, manager["user"]["id"], "editor", "user.read")

        assigned = await client.post(
            f"/api/v1/roles/{role.id}/users/{test_user_2['id']}", headers={"X-CSRF-Token": manager["csrf"]}
        )

        assert assigned.status_code == 201
        assert await _holds(db_session, test_user_2["id"], role.id)

        unassigned = await client.delete(
            f"/api/v1/roles/{role.id}/users/{test_user_2['id']}", headers={"X-CSRF-Token": manager["csrf"]}
        )

        assert unassigned.status_code == 200
        assert not await _holds(db_session, test_user_2["id"], role.id)

    async def test_assigning_twice_changes_nothing(
        self, client: AsyncClient, db_session: AsyncSession, manager: dict[str, Any], test_user_2: dict
    ):
        role = await _grant(db_session, manager["user"]["id"], "editor", "user.read")
        path = f"/api/v1/roles/{role.id}/users/{test_user_2['id']}"

        first = await client.post(path, headers={"X-CSRF-Token": manager["csrf"]})
        second = await client.post(path, headers={"X-CSRF-Token": manager["csrf"]})

        assert (first.status_code, second.status_code) == (201, 201)
        assert await _holds(db_session, test_user_2["id"], role.id)

    async def test_assigning_a_role_stronger_than_the_caller_is_refused(
        self, client: AsyncClient, db_session: AsyncSession, manager: dict[str, Any], test_user_2: dict
    ):
        """Handing someone else a stronger role is how a caller escalates by proxy."""
        stronger = await _grant(db_session, test_user_2["id"], "admins", "user.delete")
        await client.delete(f"/api/v1/roles/{stronger.id}/users/{test_user_2['id']}", headers={"X-CSRF-Token": manager["csrf"]})

        response = await client.post(
            f"/api/v1/roles/{stronger.id}/users/{manager['user']['id']}", headers={"X-CSRF-Token": manager["csrf"]}
        )

        assert response.status_code == 403
        assert not await _holds(db_session, manager["user"]["id"], stronger.id)

    async def test_an_account_that_does_not_exist_is_a_404(
        self, client: AsyncClient, db_session: AsyncSession, manager: dict[str, Any]
    ):
        role = await _grant(db_session, manager["user"]["id"], "editor", "user.read")

        response = await client.post(f"/api/v1/roles/{role.id}/users/999999", headers={"X-CSRF-Token": manager["csrf"]})

        assert response.status_code == 404

    async def test_without_the_permission_assigning_is_refused(
        self, client: AsyncClient, db_session: AsyncSession, test_user: dict, test_user_2: dict
    ):
        role = await _grant(db_session, test_user["id"], "reader", "role.read")
        csrf = await _login(client, test_user)

        response = await client.post(f"/api/v1/roles/{role.id}/users/{test_user_2['id']}", headers={"X-CSRF-Token": csrf})

        assert response.status_code == 403
        assert not await _holds(db_session, test_user_2["id"], role.id)


class TestWritesThatRace:
    """Two writes to one role arrive at once, and the loser is answered rather than 500ed."""

    @pytest.fixture
    async def racing_manager(self, a_session_per_request: AsyncClient, db_session: AsyncSession, test_user: dict) -> str:
        """The managing caller, signed in on the client whose requests run at once."""
        await _grant(db_session, test_user["id"], "role-manager", *MANAGING, "user.read")

        return await _login(a_session_per_request, test_user)

    @pytest.fixture
    def both_authorized_at_once(self, monkeypatch) -> None:
        """Hold each request at the end of its permission lookup until the other is there.

        The lookup runs once per request, before the route reads a role, so neither has
        touched one when they are let go: that is the moment two writes meet.
        """
        both = asyncio.Barrier(2)
        resolve = authz.load_permissions

        async def waiting_for_the_other(db, user_id, **asked):
            held = await resolve(db, user_id, **asked)
            async with asyncio.timeout(10):
                await both.wait()

            return held

        monkeypatch.setattr(authz, "load_permissions", waiting_for_the_other)

    async def test_two_assignments_of_one_role_to_one_account_both_answer(
        self,
        a_session_per_request: AsyncClient,
        db_session: AsyncSession,
        test_user: dict,
        test_user_2: dict,
        racing_manager: str,
        both_authorized_at_once: None,
    ):
        """Both used to check the table before inserting, so the loser hit the primary key."""
        role = await _grant(db_session, test_user["id"], "editor", "user.read")
        path = f"/api/v1/roles/{role.id}/users/{test_user_2['id']}"

        answers = await asyncio.gather(
            *(a_session_per_request.post(path, headers={"X-CSRF-Token": racing_manager}) for _ in range(2))
        )

        assert [answer.status_code for answer in answers] == [201, 201]
        assert await _holders_of(db_session, role.id) == sorted([test_user["id"], test_user_2["id"]])

    async def test_two_replacements_of_what_one_role_carries_both_answer(
        self,
        a_session_per_request: AsyncClient,
        db_session: AsyncSession,
        test_user: dict,
        racing_manager: str,
        both_authorized_at_once: None,
    ):
        """Each deletes what the role carries and inserts its own, which collided."""
        role = await _grant(db_session, test_user["id"], "editor", "user.read")
        path = f"/api/v1/roles/{role.id}/permissions"
        sets = (["user.read"], ["role.read"])

        answers = await asyncio.gather(
            *(
                a_session_per_request.put(path, json={"permissions": carried}, headers={"X-CSRF-Token": racing_manager})
                for carried in sets
            )
        )

        assert [answer.status_code for answer in answers] == [200, 200]
        assert await _carried(db_session, role.id) in [sorted(carried) for carried in sets]

    async def test_an_assignment_racing_the_deletion_of_the_role_is_answered(
        self,
        a_session_per_request: AsyncClient,
        db_session: AsyncSession,
        test_user: dict,
        test_user_2: dict,
        racing_manager: str,
        both_authorized_at_once: None,
    ):
        """The assignment's row points at a role the deletion is taking away.

        Whichever order they land in is sound: the assignment either goes in and the
        deletion takes it with the role, or it finds no role to assign and answers 404.
        """
        role = await _grant(db_session, test_user["id"], "editor", "user.read")
        headers = {"X-CSRF-Token": racing_manager}

        assigned, deleted = await asyncio.gather(
            a_session_per_request.post(f"/api/v1/roles/{role.id}/users/{test_user_2['id']}", headers=headers),
            a_session_per_request.delete(f"/api/v1/roles/{role.id}", headers=headers),
        )

        assert deleted.status_code == 200
        assert assigned.status_code in (201, 404)
        assert await _role_named(db_session, "editor") is None
        assert await _holders_of(db_session, role.id) == []

    async def test_replacing_what_a_role_carries_while_it_is_deleted_is_answered(
        self,
        a_session_per_request: AsyncClient,
        db_session: AsyncSession,
        test_user: dict,
        racing_manager: str,
        both_authorized_at_once: None,
    ):
        """The permissions being written belong to a role the deletion is taking away."""
        role = await _grant(db_session, test_user["id"], "editor", "user.read")
        headers = {"X-CSRF-Token": racing_manager}

        replaced, deleted = await asyncio.gather(
            a_session_per_request.put(
                f"/api/v1/roles/{role.id}/permissions", json={"permissions": ["role.read"]}, headers=headers
            ),
            a_session_per_request.delete(f"/api/v1/roles/{role.id}", headers=headers),
        )

        assert deleted.status_code == 200
        assert replaced.status_code in (200, 404)
        assert await _role_named(db_session, "editor") is None
        assert await _carried(db_session, role.id) == []

    async def test_a_role_is_not_deleted_from_under_an_account_the_caller_cannot_reach(
        self,
        a_session_per_request: AsyncClient,
        db_session: AsyncSession,
        test_user: dict,
        test_user_2: dict,
        test_superuser: dict,
        racing_manager: str,
        both_authorized_at_once: None,
    ):
        """Deleting a role takes it from every holder, so a stronger holder refuses it.

        The holder arrives while the deletion is being authorized: a superuser is assigning
        the role to an account the manager could not have assigned it to. Either the
        deletion was first and the assignment finds no role, or the assignment was first
        and the deletion is refused the role it may no longer reach.
        """
        role = await _grant(db_session, test_user["id"], "editor", "user.read")
        await _grant(db_session, test_user_2["id"], "deleters", "user.delete")

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as superuser_client:
            theirs = await _login(superuser_client, test_superuser)

            assigned, deleted = await asyncio.gather(
                superuser_client.post(f"/api/v1/roles/{role.id}/users/{test_user_2['id']}", headers={"X-CSRF-Token": theirs}),
                a_session_per_request.delete(f"/api/v1/roles/{role.id}", headers={"X-CSRF-Token": racing_manager}),
            )

        assert (deleted.status_code, assigned.status_code) in ((200, 404), (403, 201))
        if deleted.status_code == 403:
            assert await _holders_of(db_session, role.id) == sorted([test_user["id"], test_user_2["id"]])
        else:
            assert await _role_named(db_session, "editor") is None

    async def test_an_account_deleted_once_the_checks_have_passed_is_a_404(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        manager: dict[str, Any],
        test_user_2: dict,
        monkeypatch,
    ):
        """The admin panel deletes account rows, and an assignment's key needs one.

        The check that the account is reachable answers truthfully, and the row is gone by
        the time the assignment is written: the role's lock holds the role still, nothing
        holds the account. The panel's own delete is what the second session runs here.
        """
        role_id = (await _grant(db_session, manager["user"]["id"], "editor", "user.read")).id
        reachable = role_service.can_change_roles_of
        sessions = async_sessionmaker(bind=db_session.bind, class_=AsyncSession, expire_on_commit=False)

        async def deleted_right_after(db: AsyncSession, principal: Principal, user_id: int, held: Any) -> bool:
            allowed: bool = await reachable(db, principal, user_id, held)
            async with sessions() as panel:
                await panel.execute(delete(User).where(User.id == user_id))
                await panel.commit()

            return allowed

        monkeypatch.setattr(role_service, "can_change_roles_of", deleted_right_after)

        response = await client.post(
            f"/api/v1/roles/{role_id}/users/{test_user_2['id']}", headers={"X-CSRF-Token": manager["csrf"]}
        )

        assert response.status_code == 404
        assert await _holders_of(db_session, role_id) == [manager["user"]["id"]]


class TestReadingAUsersRoles:
    """The roles an account holds, for whoever may read roles."""

    async def test_a_holder_reads_another_accounts_roles(
        self, client: AsyncClient, db_session: AsyncSession, manager: dict[str, Any], test_user_2: dict
    ):
        await _grant(db_session, test_user_2["id"], "editor", "user.read")

        response = await client.get(f"/api/v1/users/{test_user_2['id']}/roles", headers={"X-CSRF-Token": manager["csrf"]})

        assert response.status_code == 200
        assert [(role["name"], role["permissions"]) for role in response.json()] == [("editor", ["user.read"])]

    async def test_an_account_that_does_not_exist_is_a_404(self, client: AsyncClient, manager: dict[str, Any]):
        assert (await client.get("/api/v1/users/999999/roles")).status_code == 404

    async def test_without_the_permission_it_is_refused(
        self, client: AsyncClient, db_session: AsyncSession, test_user: dict, test_user_2: dict
    ):
        await _login(client, test_user)

        assert (await client.get(f"/api/v1/users/{test_user_2['id']}/roles")).status_code == 403
