"""The tier-limits resolver: the caller's configured limit for the path, if there is one."""

from types import SimpleNamespace

from crudauth import Principal

from src.infrastructure.database.session import async_session
from src.modules.rate_limit.crud import crud_rate_limits
from src.modules.rate_limit.hooks import tier_rate_limit

_SENTINEL_DB = object()


def _request_for(path: str, override):
    return SimpleNamespace(
        url=SimpleNamespace(path=path),
        app=SimpleNamespace(dependency_overrides={async_session: override}),
    )


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
    assert (result.times, result.seconds) == (2, 3600)


async def test_a_caller_without_a_tier_declines(monkeypatch):
    assert await tier_rate_limit(SimpleNamespace(url=None, app=None), None) is None


async def test_a_principal_without_a_loaded_user_declines(monkeypatch):
    principal = Principal(user_id=1, user=None, transport="session")

    assert await tier_rate_limit(SimpleNamespace(url=None, app=None), principal) is None


async def test_a_tier_without_a_row_for_the_path_declines(monkeypatch):
    """Declining leaves the default limit to the throttle itself."""

    async def override_session():
        yield _SENTINEL_DB

    async def fake_get(db, **kwargs):
        return None

    monkeypatch.setattr(crud_rate_limits, "get", fake_get)
    principal = Principal(user_id=1, user=SimpleNamespace(tier_id=7), transport="session")

    assert await tier_rate_limit(_request_for("/api/v1/tiers/", override_session), principal) is None
