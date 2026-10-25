"""What a cached response is keyed by, and when it is served."""

from collections.abc import Callable
from typing import Annotated, Any
from unittest.mock import AsyncMock, patch

import pytest
from crudauth import Principal
from fastapi import Depends, Query, Request
from fastapi.routing import APIRoute
from pydantic import BaseModel, Field

from src.infrastructure.auth.scope import SCOPE_OWNER_IS_SUPERUSER
from src.infrastructure.cache.decorator import cache
from src.infrastructure.cache.exceptions import InvalidRequestError
from src.infrastructure.uncached import cached as uncached

pytestmark = pytest.mark.asyncio

ALICE = Principal(user_id=1, transport="session")
BOB = Principal(user_id=2, transport="session")


def _request(method: str = "GET", query: str = "", route: Callable[..., Any] | None = None) -> Request:
    """A request the decorator can read a method, a query string and its route off.

    The route is what the query parameters are read from, so a request carrying a query
    arrives through one, built over the endpoint the way the router builds it.
    """
    scope: dict[str, Any] = {
        "type": "http",
        "method": method,
        "path": "/items",
        "raw_path": b"/items",
        "query_string": query.encode(),
        "headers": [],
        "client": ("127.0.0.1", 1234),
        "server": ("test", 80),
        "scheme": "http",
    }
    if route is not None:
        scope["route"] = APIRoute("/items", route, methods=[method])

    return Request(scope)


@pytest.fixture
def backend():
    """A cache backend that records what it was asked for."""
    recorded = AsyncMock()
    recorded.get = AsyncMock(return_value=None)
    recorded.set = AsyncMock()
    recorded.delete = AsyncMock()
    recorded.delete_pattern = AsyncMock()

    with patch("src.infrastructure.cache.decorator.cache_provider") as provider:
        provider.get_backend.return_value = recorded
        yield recorded


class TestWhatTheKeyIsMadeOf:
    """A cached response must not be served for a different page, or a different caller."""

    async def test_a_shared_route_is_keyed_by_prefix_and_resource(self, backend):
        @cache(key_prefix="tiers", resource_id_name="item_id", per_caller=False)
        async def endpoint(request: Request, item_id: int) -> dict[str, Any]:
            return {"data": "fresh"}

        await endpoint(_request(), item_id=123)

        backend.get.assert_called_once_with("tiers:123")

    async def test_the_query_is_part_of_the_key(self, backend):
        @cache(key_prefix="tiers", per_caller=False)
        async def endpoint(request: Request, page: int, items_per_page: int) -> dict[str, Any]:
            return {"page": page}

        await endpoint(_request(query="page=1&items_per_page=10", route=endpoint), page=1, items_per_page=10)
        await endpoint(_request(query="page=2&items_per_page=10", route=endpoint), page=2, items_per_page=10)

        asked = [call.args[0] for call in backend.get.call_args_list]
        assert asked == ["tiers:q=items_per_page=10&page=1", "tiers:q=items_per_page=10&page=2"]

    async def test_two_orderings_of_one_query_share_an_entry(self, backend):
        @cache(key_prefix="tiers", per_caller=False)
        async def endpoint(request: Request, page: int, items_per_page: int) -> dict[str, Any]:
            return {"page": page}

        await endpoint(_request(query="page=1&items_per_page=10", route=endpoint), page=1, items_per_page=10)
        await endpoint(_request(query="items_per_page=10&page=1", route=endpoint), page=1, items_per_page=10)

        asked = {call.args[0] for call in backend.get.call_args_list}
        assert asked == {"tiers:q=items_per_page=10&page=1"}

    async def test_a_parameter_the_route_does_not_declare_is_no_part_of_the_key(self, backend):
        """It cannot have changed the answer, so it must not store an answer of its own."""

        @cache(key_prefix="tiers", per_caller=False)
        async def endpoint(request: Request, page: int) -> dict[str, Any]:
            return {"page": page}

        await endpoint(_request(query="page=1", route=endpoint), page=1)
        await endpoint(_request(query="page=1&utm_source=newsletter", route=endpoint), page=1)

        asked = {call.args[0] for call in backend.get.call_args_list}
        assert asked == {"tiers:q=page=1"}

    async def test_a_query_spelling_the_delimiters_is_not_the_query_it_spells(self, backend):
        """``?items_per_page%3D20%26page=1`` carries one parameter, named with an escaped pair.

        Written into a key as it came, that name reads as the two parameters it spells, so
        a request for anything at all is stored under the entry a real request for that
        page is served from.
        """

        @cache(key_prefix="tiers", per_caller=False)
        async def endpoint(request: Request, page: int = 1, items_per_page: int = 10) -> dict[str, Any]:
            return {"page": page}

        await endpoint(_request(query="items_per_page%3D20%26page=1", route=endpoint), page=1, items_per_page=10)
        await endpoint(_request(query="items_per_page=20&page=1", route=endpoint), page=1, items_per_page=20)

        crafted, real = (call.args[0] for call in backend.get.call_args_list)
        assert crafted != real

    async def test_a_scoped_credential_does_not_share_an_entry_with_its_owners_session(self, backend):
        """A key holds its owner's permissions narrowed, so a response made for the owner's
        session is not one it may be served.
        """
        session = Principal(user_id=1, transport="session")
        scoped = Principal(user_id=1, transport="apikey", scopes=("user.read",), metadata={SCOPE_OWNER_IS_SUPERUSER: False})

        @cache(key_prefix="keys", resource_id_name="item_id", caller_from="principal")
        async def endpoint(request: Request, item_id: int, principal: Principal) -> dict[str, Any]:
            return {"ok": True}

        await endpoint(_request(), item_id=7, principal=session)
        await endpoint(_request(), item_id=7, principal=scoped)

        asked = [call.args[0] for call in backend.get.call_args_list]
        assert asked[0] != asked[1]

    async def test_each_caller_gets_their_own_entry(self, backend):
        @cache(key_prefix="keys", resource_id_name="item_id", caller_from="principal")
        async def endpoint(request: Request, item_id: int, principal: Principal) -> dict[str, Any]:
            return {"for": principal.user_id}

        await endpoint(_request(), item_id=7, principal=ALICE)
        await endpoint(_request(), item_id=7, principal=BOB)

        asked = [call.args[0] for call in backend.get.call_args_list]
        assert asked == ["keys:7:u=1", "keys:7:u=2"]

    async def test_a_caller_that_is_not_a_principal_is_not_cached(self, backend):
        """An account read any other way says nothing about which credential asked.

        A current-user mapping is the account itself, so a key scoped to reading and its
        owner's session would both be stored under the account, and one would be served the
        other's response.
        """
        calls: list[int] = []

        @cache(key_prefix="keys", resource_id_name="item_id", caller_from="current_user")
        async def endpoint(request: Request, item_id: int, current_user: dict[str, Any]) -> dict[str, Any]:
            calls.append(item_id)
            return {"for": current_user["username"]}

        await endpoint(_request(), item_id=7, current_user={"id": 1, "username": "alice"})
        await endpoint(_request(), item_id=7, current_user={"id": 1, "username": "alice"})

        assert calls == [7, 7]
        backend.get.assert_not_called()
        backend.set.assert_not_called()

    async def test_a_parameter_under_an_alias_is_part_of_the_key(self, backend):
        """It arrives under the alias and lands in an argument of another name."""

        @cache(key_prefix="tiers", per_caller=False)
        async def endpoint(request: Request, items_per_page: Annotated[int, Query(alias="items-per-page")] = 10):
            return {"items_per_page": items_per_page}

        await endpoint(_request(query="items-per-page=10", route=endpoint), items_per_page=10)
        await endpoint(_request(query="items-per-page=20", route=endpoint), items_per_page=20)

        asked = [call.args[0] for call in backend.get.call_args_list]
        assert asked == ["tiers:q=items-per-page=10", "tiers:q=items-per-page=20"]

    async def test_a_parameter_a_dependency_reads_is_part_of_the_key(self, backend):
        """It is no argument of the route at all, so two pages would share one entry."""

        class Pagination:
            def __init__(self, page: int = 1, items_per_page: int = 10) -> None:
                self.page = page

        @cache(key_prefix="tiers", per_caller=False)
        async def endpoint(request: Request, pages: Annotated[Pagination, Depends()]) -> dict[str, Any]:
            return {"page": pages.page}

        await endpoint(_request(query="page=1", route=endpoint), pages=Pagination(page=1))
        await endpoint(_request(query="page=2", route=endpoint), pages=Pagination(page=2))

        asked = [call.args[0] for call in backend.get.call_args_list]
        assert asked == ["tiers:q=page=1", "tiers:q=page=2"]

    async def test_a_per_caller_route_with_no_caller_is_not_cached(self, backend):
        """Sharing one entry between callers is the mistake this refuses to make."""
        calls: list[int] = []

        @cache(key_prefix="keys", resource_id_name="item_id", caller_from="current_user")
        async def endpoint(request: Request, item_id: int) -> dict[str, Any]:
            calls.append(item_id)
            return {"ok": True}

        await endpoint(_request(), item_id=7)
        await endpoint(_request(), item_id=7)

        assert calls == [7, 7]
        backend.get.assert_not_called()
        backend.set.assert_not_called()

    async def test_the_parameters_a_query_model_carries_are_part_of_the_key(self, backend):
        """The route declares one parameter, named after an argument no query ever carries."""

        class Filters(BaseModel):
            page: int = 1
            size: Annotated[int, Field(alias="items-per-page")] = 10

        @cache(key_prefix="tiers", per_caller=False)
        async def endpoint(request: Request, filters: Annotated[Filters, Query()]) -> dict[str, Any]:
            return {"page": filters.page}

        await endpoint(_request(query="page=1", route=endpoint), filters=Filters(page=1))
        await endpoint(_request(query="page=2", route=endpoint), filters=Filters(page=2))
        await endpoint(_request(query="items-per-page=20", route=endpoint), filters=Filters(**{"items-per-page": 20}))

        asked = [call.args[0] for call in backend.get.call_args_list]
        assert asked == ["tiers:q=page=1", "tiers:q=page=2", "tiers:q=items-per-page=20"]

    async def test_a_request_with_no_route_to_read_keeps_every_parameter(self, backend):
        """Nothing says which parameters count, so a key too many beats serving one answer twice."""

        @cache(key_prefix="tiers", per_caller=False)
        async def endpoint(request: Request, page: int) -> dict[str, Any]:
            return {"page": page}

        await endpoint(_request(query="page=1&anything=1"), page=1)
        await endpoint(_request(query="page=2&anything=1"), page=2)

        asked = [call.args[0] for call in backend.get.call_args_list]
        assert asked == ["tiers:q=anything=1&page=1", "tiers:q=anything=1&page=2"]

    async def test_a_per_caller_route_that_names_no_caller_is_a_programming_error(self):
        """Which argument identifies the caller is the route's to say, at import time."""
        with pytest.raises(ValueError, match="must name the argument"):

            @cache(key_prefix="keys", resource_id_name="item_id")
            async def endpoint(request: Request, item_id: int) -> dict[str, Any]:
                return {"ok": True}


class TestWhatIsServedFromTheCache:
    """An entry is served whenever one is stored, including when what was stored is empty."""

    async def test_a_stored_response_is_served_without_the_route(self, backend):
        backend.get.return_value = {"data": "cached"}

        @cache(key_prefix="tiers", resource_id_name="item_id", per_caller=False)
        async def endpoint(request: Request, item_id: int) -> dict[str, Any]:
            raise AssertionError("the route ran despite a stored response")

        assert await endpoint(_request(), item_id=123) == {"data": "cached"}
        backend.set.assert_not_called()

    async def test_a_missing_entry_runs_the_route_and_stores_what_it_answered(self, backend):
        @cache(key_prefix="tiers", resource_id_name="item_id", per_caller=False)
        async def endpoint(request: Request, item_id: int) -> dict[str, Any]:
            return {"data": "fresh"}

        assert await endpoint(_request(), item_id=123) == {"data": "fresh"}
        backend.set.assert_called_once()

    @pytest.mark.parametrize("empty", [[], {}, ""])
    async def test_an_empty_answer_is_stored_and_then_served(self, backend, empty: Any):
        """A page with nothing on it used to be re-read on every request."""
        runs: list[int] = []

        @cache(key_prefix="tiers", resource_id_name="item_id", per_caller=False)
        async def endpoint(request: Request, item_id: int) -> Any:
            runs.append(item_id)
            return empty

        first = await endpoint(_request(), item_id=123)
        backend.get.return_value = backend.set.call_args.args[1]
        second = await endpoint(_request(), item_id=123)

        assert (first, second) == (empty, empty)
        assert runs == [123]


class TestInvalidation:
    """A write clears what it made stale."""

    async def test_a_write_deletes_the_entry_it_wrote_over(self, backend):
        @cache(key_prefix="tiers", resource_id_name="item_id", per_caller=False)
        async def endpoint(request: Request, item_id: int) -> dict[str, Any]:
            return {"data": "updated"}

        await endpoint(_request(method="PUT"), item_id=123)

        backend.get.assert_not_called()
        backend.set.assert_not_called()
        backend.delete.assert_called_once_with("tiers:123")

    async def test_a_write_deletes_the_extra_keys_it_was_given(self, backend):
        @cache(
            key_prefix="tiers",
            resource_id_name="item_id",
            to_invalidate_extra={"related": "related_id"},
            per_caller=False,
        )
        async def endpoint(request: Request, item_id: int, related_id: int) -> dict[str, Any]:
            return {"data": "updated"}

        await endpoint(_request(method="PUT"), item_id=123, related_id=456)

        backend.delete.assert_any_call("tiers:123")
        backend.delete.assert_any_call("related:456")

    async def test_a_write_clears_every_page_of_a_listing(self, backend):
        """The pages are keyed by their query, so only a pattern reaches all of them."""

        @cache(
            key_prefix="tiers",
            resource_id_name="item_id",
            pattern_to_invalidate_extra=["tiers:*"],
            per_caller=False,
        )
        async def endpoint(request: Request, item_id: int) -> dict[str, Any]:
            return {"data": "updated"}

        await endpoint(_request(method="PUT"), item_id=123)

        backend.delete.assert_called_once_with("tiers:123")
        backend.delete_pattern.assert_called_once_with("tiers:*")

    async def test_a_read_that_asks_to_invalidate_is_a_programming_error(self, backend):
        @cache(
            key_prefix="tiers",
            resource_id_name="item_id",
            to_invalidate_extra={"related": "related_id"},
            per_caller=False,
        )
        async def endpoint(request: Request, item_id: int, related_id: int) -> dict[str, Any]:
            return {"data": "value"}

        with pytest.raises(InvalidRequestError):
            await endpoint(_request(), item_id=123, related_id=456)


class TestABackendThatIsDown:
    """A cache the route cannot reach must not become the route's own failure."""

    async def test_a_read_that_raises_falls_through_to_the_route(self, backend):
        backend.get.side_effect = ConnectionError("redis is gone")

        @cache(key_prefix="tiers", resource_id_name="item_id", per_caller=False)
        async def endpoint(request: Request, item_id: int) -> dict[str, Any]:
            return {"data": "fresh"}

        assert await endpoint(_request(), item_id=123) == {"data": "fresh"}

    async def test_a_write_that_raises_still_answers(self, backend):
        backend.set.side_effect = ConnectionError("redis is gone")

        @cache(key_prefix="tiers", resource_id_name="item_id", per_caller=False)
        async def endpoint(request: Request, item_id: int) -> dict[str, Any]:
            return {"data": "fresh"}

        assert await endpoint(_request(), item_id=123) == {"data": "fresh"}

    async def test_an_invalidation_that_raises_still_answers(self, backend):
        backend.delete.side_effect = ConnectionError("redis is gone")

        @cache(key_prefix="tiers", resource_id_name="item_id", per_caller=False)
        async def endpoint(request: Request, item_id: int) -> dict[str, Any]:
            return {"data": "updated"}

        assert await endpoint(_request(method="PUT"), item_id=123) == {"data": "updated"}


class TestAProjectWithoutTheCacheFeature:
    """The wiring hands such a project a decorator that caches nothing."""

    async def test_the_route_is_left_as_it_is(self):
        calls: list[int] = []

        @uncached(key_prefix="tiers", resource_id_name="item_id", per_caller=False)
        async def endpoint(request: Request, item_id: int) -> dict[str, Any]:
            calls.append(item_id)
            return {"data": "fresh"}

        first = await endpoint(_request(), item_id=123)
        second = await endpoint(_request(), item_id=123)

        assert (first, second) == ({"data": "fresh"}, {"data": "fresh"})
        assert calls == [123, 123]
