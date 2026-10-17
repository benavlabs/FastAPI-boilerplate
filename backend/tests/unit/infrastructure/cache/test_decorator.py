"""What a cached response is keyed by, and when it is served."""

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import Request

from src.infrastructure.cache.decorator import cache
from src.infrastructure.cache.exceptions import InvalidRequestError
from src.infrastructure.uncached import cached as uncached

pytestmark = pytest.mark.asyncio

ALICE = {"id": 1, "username": "alice"}
BOB = {"id": 2, "username": "bob"}


def _request(method: str = "GET", query: str = "") -> Request:
    """A request the decorator can read a method and a query string off."""
    return Request(
        {
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
    )


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
        async def endpoint(request: Request, page: int) -> dict[str, Any]:
            return {"page": page}

        await endpoint(_request(query="page=1&items_per_page=10"), page=1)
        await endpoint(_request(query="page=2&items_per_page=10"), page=2)

        asked = [call.args[0] for call in backend.get.call_args_list]
        assert asked == ["tiers:1:q=items_per_page=10&page=1", "tiers:2:q=items_per_page=10&page=2"]

    async def test_two_orderings_of_one_query_share_an_entry(self, backend):
        @cache(key_prefix="tiers", per_caller=False)
        async def endpoint(request: Request, page: int) -> dict[str, Any]:
            return {"page": page}

        await endpoint(_request(query="a=1&b=2"), page=1)
        await endpoint(_request(query="b=2&a=1"), page=1)

        asked = {call.args[0] for call in backend.get.call_args_list}
        assert asked == {"tiers:1:q=a=1&b=2"}

    async def test_each_caller_gets_their_own_entry(self, backend):
        @cache(key_prefix="keys", resource_id_name="item_id")
        async def endpoint(request: Request, item_id: int, current_user: dict[str, Any]) -> dict[str, Any]:
            return {"for": current_user["username"]}

        await endpoint(_request(), item_id=7, current_user=ALICE)
        await endpoint(_request(), item_id=7, current_user=BOB)

        asked = [call.args[0] for call in backend.get.call_args_list]
        assert asked == ["keys:7:u=1", "keys:7:u=2"]

    async def test_a_principal_names_the_caller_too(self, backend):
        class _Principal:
            user_id = 42

        @cache(key_prefix="keys", resource_id_name="item_id")
        async def endpoint(request: Request, item_id: int, principal: _Principal) -> dict[str, Any]:
            return {"ok": True}

        await endpoint(_request(), item_id=7, principal=_Principal())

        backend.get.assert_called_once_with("keys:7:u=42")

    async def test_a_per_caller_route_with_no_caller_is_not_cached(self, backend):
        """Sharing one entry between callers is the mistake this refuses to make."""
        calls: list[int] = []

        @cache(key_prefix="keys", resource_id_name="item_id")
        async def endpoint(request: Request, item_id: int) -> dict[str, Any]:
            calls.append(item_id)
            return {"ok": True}

        await endpoint(_request(), item_id=7)
        await endpoint(_request(), item_id=7)

        assert calls == [7, 7]
        backend.get.assert_not_called()
        backend.set.assert_not_called()


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
