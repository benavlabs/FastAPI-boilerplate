"""The principal a key resolves, and what the gates make of it."""

import pytest
from crudauth import Principal
from crudauth.exceptions import ForbiddenException

from src.infrastructure.auth import dependencies as deps
from src.infrastructure.auth.scope import SCOPE_OWNER_IS_SUPERUSER, carries_a_scope, owner_is_superuser


def _scoped(*, is_superuser: bool) -> Principal:
    """A principal shaped as ``APIKeyTransport`` builds one for a superuser's key."""
    return Principal(
        user_id=1,
        transport="apikey",
        is_superuser=False,
        scopes=("user.read",),
        metadata={"api_key_id": 7, SCOPE_OWNER_IS_SUPERUSER: is_superuser},
    )


def test_the_metadata_marks_the_credential_as_scoped():
    assert carries_a_scope(_scoped(is_superuser=False))
    assert not carries_a_scope(Principal(user_id=1, transport="session", is_superuser=True))


def test_the_owners_flag_is_readable_only_through_the_metadata():
    """The narrowing needs it; nothing else does, and the principal never carries it."""
    scoped = _scoped(is_superuser=True)

    assert scoped.is_superuser is False
    assert owner_is_superuser(scoped) is True
    assert owner_is_superuser(_scoped(is_superuser=False)) is False


@pytest.mark.asyncio
async def test_the_superuser_gate_refuses_a_credential_carrying_a_scope():
    """Even shaped like a superuser's, which a transport that forgot to zero it would be."""
    user = {"id": 1, "is_superuser": True}
    pretending = Principal(
        user_id=1,
        transport="apikey",
        is_superuser=True,
        scopes=("user.read",),
        metadata={SCOPE_OWNER_IS_SUPERUSER: True},
    )

    with pytest.raises(ForbiddenException):
        await deps.get_current_superuser(principal=pretending, current_user=user)
