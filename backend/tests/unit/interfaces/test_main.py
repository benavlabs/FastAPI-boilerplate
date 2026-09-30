"""The lifespan the app actually runs, as ``main`` assembles it."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.infrastructure.composition import ReadinessCheck
from src.infrastructure.config.settings import settings
from src.infrastructure.readiness import forget_cached_report
from src.interfaces import main

pytestmark = pytest.mark.asyncio


async def test_the_startup_table_creation_follows_the_setting(monkeypatch):
    """A project that manages its schema elsewhere must be able to turn this off."""
    monkeypatch.setattr(settings, "CREATE_TABLES_ON_STARTUP", False)

    with patch("src.infrastructure.app_factory.create_tables", AsyncMock()) as create_tables:
        async with main.lifespan_with_security(FastAPI()):
            pass

    create_tables.assert_not_awaited()


async def test_tables_are_created_when_the_setting_asks_for_it(monkeypatch):
    monkeypatch.setattr(settings, "CREATE_TABLES_ON_STARTUP", True)

    with patch("src.infrastructure.app_factory.create_tables", AsyncMock()) as create_tables:
        async with main.lifespan_with_security(FastAPI()):
            pass

    create_tables.assert_awaited_once()


@pytest.fixture(autouse=True)
def forget_the_readiness_report():
    """The report is remembered for a couple of seconds, which tests must not inherit."""
    forget_cached_report()
    yield
    forget_cached_report()


async def test_readiness_reports_every_dependency(monkeypatch):
    """A project answers for whatever it selected, and nothing else."""
    checked: list[str] = []

    async def reachable() -> None:
        checked.append("asked")

    monkeypatch.setattr(main, "READINESS_CHECKS", (ReadinessCheck("database", reachable),))

    async with AsyncClient(transport=ASGITransport(app=main.app), base_url="http://test") as client:
        response = await client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "dependencies": {"database": "ready"}}
    assert checked == ["asked"]


async def test_readiness_holds_traffic_back_when_a_dependency_is_down(monkeypatch):
    async def reachable() -> None:
        return None

    async def unreachable() -> None:
        raise ConnectionError("no route to host")

    monkeypatch.setattr(
        main,
        "READINESS_CHECKS",
        (ReadinessCheck("database", reachable), ReadinessCheck("cache", unreachable)),
    )

    async with AsyncClient(transport=ASGITransport(app=main.app), base_url="http://test") as client:
        response = await client.get("/health/ready")

    assert response.status_code == 503
    assert response.json()["dependencies"] == {"database": "ready", "cache": "unavailable"}


async def test_liveness_answers_without_touching_a_dependency(monkeypatch):
    async def explode() -> None:
        raise AssertionError("liveness must not reach for anything")

    monkeypatch.setattr(main, "READINESS_CHECKS", (ReadinessCheck("database", explode),))

    async with AsyncClient(transport=ASGITransport(app=main.app), base_url="http://test") as client:
        response = await client.get("/health")

    assert response.status_code == 200
