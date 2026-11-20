"""A credential that carries a scope is cached apart from its account's other credentials."""

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from crudauth import Principal
from fastapi import Request

from src.infrastructure.auth.scope import SCOPE_OWNER_IS_SUPERUSER
from src.infrastructure.cache.decorator import cache
from src.infrastructure.cache.utils import caller_marks


def _scoped(*scope: str) -> Principal:
    """A principal shaped as the API-key transport builds one."""
    return Principal(user_id=7, transport="apikey", scopes=scope, metadata={"api_key_id": 1, SCOPE_OWNER_IS_SUPERUSER: False})


def test_a_credential_that_carries_a_scope_is_marked_apart_from_the_account():
    """A key holds its owner's permissions narrowed, so what it is served is its own."""
    marked = caller_marks(_scoped("user.read"))

    assert marked != "7"
    assert marked is not None and marked.startswith("7/")


def test_two_scopes_of_one_account_are_marked_apart():
    assert caller_marks(_scoped("user.read")) != caller_marks(_scoped("user.read", "user.update"))


def test_one_scope_written_in_either_order_is_marked_the_same():
    """The order the names were stored in is the client's, and holds the same permissions."""
    assert caller_marks(_scoped("user.read", "user.update")) == caller_marks(_scoped("user.update", "user.read"))


@pytest.mark.asyncio
async def test_a_scoped_credential_does_not_share_an_entry_with_its_owners_session():
    """A key holds its owner's permissions narrowed, so a response made for the owner's session
    is not one it may be served."""
    recorded = AsyncMock()
    recorded.get = AsyncMock(return_value=None)
    request = Request({"type": "http", "method": "GET", "path": "/items", "query_string": b"", "headers": []})

    @cache(key_prefix="keys", resource_id_name="item_id", caller_from="principal")
    async def endpoint(request: Request, item_id: int, principal: Principal) -> dict[str, Any]:
        return {"ok": True}

    with patch("src.infrastructure.cache.decorator.cache_provider") as provider:
        provider.get_backend.return_value = recorded
        await endpoint(request, item_id=7, principal=Principal(user_id=7, transport="session"))
        await endpoint(request, item_id=7, principal=_scoped("user.read"))

    session, scoped = (call.args[0] for call in recorded.get.call_args_list)
    assert session != scoped
