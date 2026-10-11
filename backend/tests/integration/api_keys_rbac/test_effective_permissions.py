"""A key's scope against the permissions a role grants: narrowing, and delegation.

These need both features: api_keys for the credential, rbac for a permission an ordinary
account can hold at all. The cases a superuser's key states without rbac live in
``tests/integration/api/v1/api_keys/test_effective_permissions.py``.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.role.models import Role, UserRole
from src.modules.user.models import User
from tests.integration.api.v1.api_keys.test_effective_permissions import key_for, sign_in, with_key
from tests.integration.rbac.test_user_permissions import _grant

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("fresh_login_lockout")]

READABLE = "/api/v1/users/"
HELD_BY_THE_CALLER = "/api/v1/permissions/me"


async def _role_carrying_nothing(db_session: AsyncSession) -> Role:
    """A role nobody holds, carrying no permission at all."""
    role = Role(name="harmless")
    db_session.add(role)
    await db_session.commit()

    return role


async def test_a_key_holds_only_what_its_scope_names(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, test_user_2: dict
):
    """The owner holds two permissions; the key is scoped to one of them.

    Editing somebody else's profile is what ``user.update`` gates. Editing one's own is
    gated by ownership, which a scope does not narrow.
    """
    await _grant(db_session, test_user["id"], "editor", "user.read", "user.update")
    key = await key_for(db_session, test_user["id"], "user.read")

    reading = await client.get(READABLE, headers=with_key(key))
    updating = await client.patch(f"/api/v1/users/{test_user_2['username']}", json={"name": "Renamed"}, headers=with_key(key))

    assert reading.status_code == 200
    assert updating.status_code == 403


async def test_the_same_key_widened_to_update_may_edit_another_account(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, test_user_2: dict
):
    """The control: the refusal above is the scope, not the route."""
    await _grant(db_session, test_user["id"], "editor", "user.read", "user.update")
    key = await key_for(db_session, test_user["id"], "user.read", "user.update")

    updating = await client.patch(f"/api/v1/users/{test_user_2['username']}", json={"name": "Renamed"}, headers=with_key(key))

    assert updating.status_code == 200


async def test_the_owners_session_still_holds_both(client: AsyncClient, db_session: AsyncSession, test_user: dict):
    """The control: the narrowing is the key's, not the account's."""
    await _grant(db_session, test_user["id"], "editor", "user.read", "user.update")
    await sign_in(client, test_user)

    listed = await client.get(READABLE)

    assert listed.status_code == 200
    assert (await client.get(HELD_BY_THE_CALLER)).json()["permissions"] == ["user.read", "user.update"]


async def test_an_unscoped_key_holds_nothing_beyond_identity(client: AsyncClient, db_session: AsyncSession, test_user: dict):
    await _grant(db_session, test_user["id"], "editor", "user.read")
    key = await key_for(db_session, test_user["id"])

    identity = await client.get("/api/v1/auth/me", headers=with_key(key))
    reading = await client.get(READABLE, headers=with_key(key))

    assert identity.status_code == 200
    assert identity.json()["user_id"] == test_user["id"]
    assert reading.status_code == 403
    assert (await client.get(HELD_BY_THE_CALLER, headers=with_key(key))).json()["permissions"] == []


async def test_a_permission_the_owner_loses_leaves_the_key(client: AsyncClient, db_session: AsyncSession, test_user: dict):
    """The scope narrows what the owner holds; it never grants on its own."""
    await _grant(db_session, test_user["id"], "editor", "user.read")
    key = await key_for(db_session, test_user["id"], "user.read")
    assert (await client.get(READABLE, headers=with_key(key))).status_code == 200

    await db_session.execute(delete(UserRole).where(UserRole.user_id == test_user["id"]))
    await db_session.commit()

    assert (await client.get(READABLE, headers=with_key(key))).status_code == 403
    assert (await client.get(HELD_BY_THE_CALLER, headers=with_key(key))).json()["permissions"] == []


async def test_a_superusers_key_reports_only_its_scope(client: AsyncClient, db_session: AsyncSession, test_superuser: dict):
    """A superuser holds every registered permission; the key holds the ones it names."""
    key = await key_for(db_session, test_superuser["id"], "user.read", held=frozenset({"user.read"}))

    reported = await client.get(HELD_BY_THE_CALLER, headers=with_key(key))

    assert reported.json()["permissions"] == ["user.read"]


async def test_a_superusers_key_is_held_to_its_scope_by_a_permission_gate(
    client: AsyncClient, db_session: AsyncSession, test_superuser: dict
):
    """``require_permissions`` lets a superuser's own session through without a lookup.

    A credential carrying a scope gets no such pass: the scope names ``user.read``, so the
    route gated on ``role.read`` is refused.
    """
    key = await key_for(db_session, test_superuser["id"], "user.read", held=frozenset({"user.read"}))

    gated = await client.get("/api/v1/roles/", headers=with_key(key))

    assert gated.status_code == 403


async def test_a_superusers_key_scoped_to_that_permission_passes_the_same_gate(
    client: AsyncClient, db_session: AsyncSession, test_superuser: dict
):
    """The control: the refusal above is the scope, not the gate being closed to keys."""
    key = await key_for(db_session, test_superuser["id"], "role.read", held=frozenset({"role.read"}))

    gated = await client.get("/api/v1/roles/", headers=with_key(key))

    assert gated.status_code == 200


async def test_a_key_cannot_be_scoped_beyond_what_its_creator_holds(
    client: AsyncClient, db_session: AsyncSession, test_user: dict
):
    """Through the route, as a session that holds one of the two names."""
    await db_session.execute(update(User).where(User.id == test_user["id"]).values(email_verified=True))
    await db_session.commit()
    await _grant(db_session, test_user["id"], "reader", "user.read")
    csrf = await sign_in(client, test_user)

    refused = await client.post(
        "/api/v1/api-keys/",
        json={"name": "Too Wide", "permissions": ["user.read", "user.update"]},
        headers={"X-CSRF-Token": csrf},
    )
    allowed = await client.post(
        "/api/v1/api-keys/",
        json={"name": "Just Right", "permissions": ["user.read"]},
        headers={"X-CSRF-Token": csrf},
    )

    assert refused.status_code == 403
    assert allowed.status_code == 201
    assert (await client.get("/api/v1/api-keys/")).json()["total_count"] == 1


class TestAKeyCannotEscalateThroughDelegation:
    """The role routes check delegation against what the credential holds, not the account."""

    async def test_a_superusers_key_cannot_assign_a_role_beyond_its_scope(
        self, client: AsyncClient, db_session: AsyncSession, test_superuser: dict, test_user: dict
    ):
        strong = await _grant(db_session, test_user["id"], "deleters", "user.delete")
        key = await key_for(db_session, test_superuser["id"], "role.assign", held=frozenset({"role.assign"}))

        assigned = await client.post(f"/api/v1/roles/{strong.id}/users/{test_user['id']}", headers=with_key(key))

        assert assigned.status_code == 403

    async def test_the_superusers_own_session_can_assign_it(
        self, client: AsyncClient, db_session: AsyncSession, test_superuser: dict, test_user: dict
    ):
        """The control: the refusal above is the key's scope."""
        strong = await _grant(db_session, test_user["id"], "deleters", "user.delete")
        csrf = await sign_in(client, test_superuser)

        assigned = await client.post(f"/api/v1/roles/{strong.id}/users/{test_user['id']}", headers={"X-CSRF-Token": csrf})

        assert assigned.status_code == 201

    async def test_a_key_cannot_assign_a_role_carrying_what_its_scope_lacks(
        self, client: AsyncClient, db_session: AsyncSession, test_user: dict, test_user_2: dict
    ):
        """The role carries ``user.delete``; the account receiving it holds nothing.

        Only ``can_assign_role`` can refuse this, and only by comparing against what the
        credential holds. No superuser anywhere, so the cancelled flag cannot be what
        refuses it either.
        """
        await _grant(db_session, test_user["id"], "manager", "role.assign")
        strong = await _grant(db_session, test_user["id"], "deleters", "user.delete")
        key = await key_for(db_session, test_user["id"], "role.assign", held=frozenset({"role.assign"}))

        assigned = await client.post(f"/api/v1/roles/{strong.id}/users/{test_user_2['id']}", headers=with_key(key))

        assert assigned.status_code == 403

    async def test_the_same_key_scoped_to_both_may_assign_it(
        self, client: AsyncClient, db_session: AsyncSession, test_user: dict, test_user_2: dict
    ):
        """The control: the refusal above is the scope, not the route."""
        await _grant(db_session, test_user["id"], "manager", "role.assign")
        strong = await _grant(db_session, test_user["id"], "deleters", "user.delete")
        key = await key_for(
            db_session, test_user["id"], "role.assign", "user.delete", held=frozenset({"role.assign", "user.delete"})
        )

        assigned = await client.post(f"/api/v1/roles/{strong.id}/users/{test_user_2['id']}", headers=with_key(key))

        assert assigned.status_code == 201

    async def test_a_key_cannot_touch_the_roles_of_an_account_stronger_than_its_scope(
        self, client: AsyncClient, db_session: AsyncSession, test_user: dict, test_user_2: dict
    ):
        """The role carries nothing, so only ``can_change_roles_of`` can refuse this.

        The target holds ``user.delete``, which the owner holds and the key's scope doesn't.
        """
        await _grant(db_session, test_user["id"], "manager", "role.assign", "user.delete")
        await _grant(db_session, test_user_2["id"], "deleters", "user.delete")
        harmless = await _role_carrying_nothing(db_session)
        key = await key_for(db_session, test_user["id"], "role.assign", held=frozenset({"role.assign"}))

        assigned = await client.post(f"/api/v1/roles/{harmless.id}/users/{test_user_2['id']}", headers=with_key(key))

        assert assigned.status_code == 403

    async def test_the_same_key_scoped_to_both_may_touch_them(
        self, client: AsyncClient, db_session: AsyncSession, test_user: dict, test_user_2: dict
    ):
        """The control."""
        await _grant(db_session, test_user["id"], "manager", "role.assign", "user.delete")
        await _grant(db_session, test_user_2["id"], "deleters", "user.delete")
        harmless = await _role_carrying_nothing(db_session)
        key = await key_for(
            db_session, test_user["id"], "role.assign", "user.delete", held=frozenset({"role.assign", "user.delete"})
        )

        assigned = await client.post(f"/api/v1/roles/{harmless.id}/users/{test_user_2['id']}", headers=with_key(key))

        assert assigned.status_code == 201

    async def test_a_key_cannot_create_a_role_carrying_what_its_scope_lacks(
        self, client: AsyncClient, db_session: AsyncSession, test_user: dict
    ):
        """The owner holds role.create and user.delete; the key's scope holds only the first."""
        await _grant(db_session, test_user["id"], "manager", "role.create", "user.delete")
        key = await key_for(db_session, test_user["id"], "role.create", held=frozenset({"role.create"}))

        created = await client.post(
            "/api/v1/roles/", json={"name": "deleters", "permissions": ["user.delete"]}, headers=with_key(key)
        )

        assert created.status_code == 403

    async def test_the_same_key_scoped_to_both_may_create_it(
        self, client: AsyncClient, db_session: AsyncSession, test_user: dict
    ):
        """The control."""
        await _grant(db_session, test_user["id"], "manager", "role.create", "user.delete")
        key = await key_for(
            db_session, test_user["id"], "role.create", "user.delete", held=frozenset({"role.create", "user.delete"})
        )

        created = await client.post(
            "/api/v1/roles/", json={"name": "deleters", "permissions": ["user.delete"]}, headers=with_key(key)
        )

        assert created.status_code == 201

    async def test_a_key_cannot_put_a_permission_its_scope_lacks_on_a_role(
        self, client: AsyncClient, db_session: AsyncSession, test_user: dict
    ):
        """The owner holds role.update and user.delete; the key's scope holds only the first."""
        role = await _grant(db_session, test_user["id"], "editor", "role.update", "user.delete")
        key = await key_for(db_session, test_user["id"], "role.update", held=frozenset({"role.update"}))

        widened = await client.put(
            f"/api/v1/roles/{role.id}/permissions",
            json={"permissions": ["role.update", "user.delete"]},
            headers=with_key(key),
        )

        assert widened.status_code == 403
