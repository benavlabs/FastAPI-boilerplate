"""Tests for the session eviction a confirmed address change triggers."""

from crudauth import HookContext
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.auth import setup
from src.infrastructure.auth.evictions import end_every_session_through


class TestEndingEverySession:
    """What the `on_after_email_changed` hook does."""

    def test_the_project_registers_it(self):
        assert setup.auth.hooks.on_after_email_changed is not None

    async def test_a_transport_with_no_manager_yet_ends_nothing(self):
        """`CRUDAuth` gives the transport its manager, so one it has not reached holds none."""
        unbound = setup._session_transport()
        assert unbound.manager is None

        await end_every_session_through(unbound)({"id": 1}, db=AsyncSession(), context=HookContext())
