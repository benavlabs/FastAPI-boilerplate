"""Managing roles through the API: who may, and what the delegation checks refuse.

Callers sign in for real, so the permission lookup and the escalation checks run against
the same session the routes use.
"""

from typing import Any

import pytest
from crudauth import Principal
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.role.exceptions import RoleExistsError
from src.modules.role.models import Role, RolePermission, UserRole
from src.modules.role.service import RoleService
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
