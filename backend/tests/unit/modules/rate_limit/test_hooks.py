"""The tier-limits resolver: the caller's configured limit for the path, if there is one."""

from types import SimpleNamespace
from typing import cast

from crudauth import Principal
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.session import async_session
from src.modules.rate_limit.crud import crud_rate_limits
from src.modules.rate_limit.hooks import rate_limits_reference_tier, tier_rate_limit
from src.modules.rate_limit.models import RateLimit

_SENTINEL_DB = object()


def _request_for(path: str, override, template: str | None = None) -> Request:
    return cast(
        Request,
        SimpleNamespace(
            url=SimpleNamespace(path=path),
            scope={"route": SimpleNamespace(path=template)} if template else {},
            app=SimpleNamespace(dependency_overrides={async_session: override}),
        ),
    )


def _request_without_a_tier() -> Request:
    return cast(Request, SimpleNamespace(url=None, app=None))


async def test_the_tier_row_comes_from_the_session_override(monkeypatch):
    """The lookup uses the request's own database dependency, overrides included."""
    entered: list[bool] = []

    async def override_session():
        entered.append(True)
        yield _SENTINEL_DB

    seen: dict[str, object] = {}

    async def fake_get(db, **kwargs):
        seen["db"] = db
        return {"limit": 2, "period": 3600}

    monkeypatch.setattr(crud_rate_limits, "get", fake_get)
    principal = Principal(user_id=1, user=SimpleNamespace(tier_id=7), transport="session")

    result = await tier_rate_limit(_request_for("/api/v1/tiers/", override_session), principal)

    assert entered == [True]
    assert seen["db"] is _SENTINEL_DB
    assert result is not None
    assert (result.times, result.seconds) == (2, 3600)


async def test_a_caller_without_a_tier_declines(monkeypatch):
    assert await tier_rate_limit(_request_without_a_tier(), None) is None


async def test_a_principal_without_a_loaded_user_declines(monkeypatch):
    principal = Principal(user_id=1, user=None, transport="session")

    assert await tier_rate_limit(_request_without_a_tier(), principal) is None


async def test_a_tier_without_a_row_for_the_path_declines(monkeypatch):
    """Declining leaves the default limit to the throttle itself."""

    async def override_session():
        yield _SENTINEL_DB

    async def fake_get(db, **kwargs):
        return None

    monkeypatch.setattr(crud_rate_limits, "get", fake_get)
    principal = Principal(user_id=1, user=SimpleNamespace(tier_id=7), transport="session")

    assert await tier_rate_limit(_request_for("/api/v1/tiers/", override_session), principal) is None


async def test_the_lookup_uses_the_route_template(monkeypatch):
    """A row saved for the template applies to every path that matches it."""

    async def override_session():
        yield _SENTINEL_DB

    seen: dict[str, object] = {}

    async def fake_get(db, **kwargs):
        seen.update(kwargs)
        return {"limit": 2, "period": 3600}

    monkeypatch.setattr(crud_rate_limits, "get", fake_get)
    principal = Principal(user_id=1, user=SimpleNamespace(tier_id=7), transport="session")
    request = _request_for("/api/v1/users/alice", override_session, template="/api/v1/users/{username}")

    result = await tier_rate_limit(request, principal)

    assert seen["path"] == "/api/v1/users/{username}"
    assert result is not None
    assert (result.times, result.seconds) == (2, 3600)


async def test_the_lookup_ignores_soft_deleted_rows(monkeypatch):
    async def override_session():
        yield _SENTINEL_DB

    seen: dict[str, object] = {}

    async def fake_get(db, **kwargs):
        seen.update(kwargs)
        return None

    monkeypatch.setattr(crud_rate_limits, "get", fake_get)
    principal = Principal(user_id=1, user=SimpleNamespace(tier_id=7), transport="session")

    assert await tier_rate_limit(_request_for("/api/v1/tiers/", override_session), principal) is None
    assert seen["is_deleted"] is False


class TestWhatHoldsATierBack:
    """The guard a tier delete asks, and which rows it counts."""

    async def test_a_live_rate_limit_holds_the_tier(self, db_session: AsyncSession, test_tier: dict):
        db_session.add(RateLimit(tier_id=test_tier["id"], name="live", path="/api/v1/users/", limit=2, period=3600))
        await db_session.commit()

        refusal = await rate_limits_reference_tier(test_tier, db_session)

        assert refusal is not None
        assert "rate limits" in refusal

    async def test_a_soft_deleted_rate_limit_does_not(self, db_session: AsyncSession, test_tier: dict):
        db_session.add(RateLimit(tier_id=test_tier["id"], name="gone", path="/api/v1/users/", limit=2, period=3600))
        await db_session.commit()
        await crud_rate_limits.delete(db=db_session, name="gone")

        assert await rate_limits_reference_tier(test_tier, db_session) is None

    async def test_a_tier_with_no_rate_limits_at_all_is_free(self, db_session: AsyncSession, test_tier: dict):
        assert await rate_limits_reference_tier(test_tier, db_session) is None
