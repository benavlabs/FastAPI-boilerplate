"""Unit tests for the application lifespan factory."""

import pytest
from fastapi import FastAPI

from src.infrastructure import app_factory
from src.infrastructure.config.settings import settings


@pytest.mark.asyncio
async def test_startup_failure_surfaces_the_original_error(monkeypatch):
    """A failed startup must raise the failing step's exception, not a teardown one.

    Before the initialized-flags guard, a startup failure (e.g. an unreachable DB
    in ``create_tables``) reached the ``finally`` block, where ``close_cache()``
    raised ``BackendNotFoundError`` for the never-initialized backend and masked
    the real error at the bottom of the log.
    """

    async def failing_create_tables() -> None:
        raise RuntimeError("db unreachable")

    monkeypatch.setattr(app_factory, "create_tables", failing_create_tables)

    lifespan = app_factory.lifespan_factory(settings, create_tables_on_startup=True)

    with pytest.raises(RuntimeError, match="db unreachable"):
        async with lifespan(FastAPI()):
            pass  # pragma: no cover - startup fails before the yield
