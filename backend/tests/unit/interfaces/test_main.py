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

    monkeypatch.setattr(main, "CRITICAL_READINESS_CHECKS", (ReadinessCheck("database", reachable),))
    monkeypatch.setattr(main, "INFORMATIONAL_READINESS_CHECKS", ())

    async with AsyncClient(transport=ASGITransport(app=main.app), base_url="http://test") as client:
        response = await client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}
    assert checked == ["asked"]


async def test_readiness_holds_traffic_back_when_a_critical_dependency_is_down(monkeypatch):
    async def reachable() -> None:
        return None

    async def unreachable() -> None:
        raise ConnectionError("no route to host")

    monkeypatch.setattr(
        main,
        "CRITICAL_READINESS_CHECKS",
        (ReadinessCheck("database", unreachable), ReadinessCheck("sessions", reachable)),
    )
    monkeypatch.setattr(main, "INFORMATIONAL_READINESS_CHECKS", ())

    async with AsyncClient(transport=ASGITransport(app=main.app), base_url="http://test") as client:
        response = await client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "not ready"}


async def test_liveness_answers_without_touching_a_dependency(monkeypatch):
    async def explode() -> None:
        raise AssertionError("liveness must not reach for anything")

    monkeypatch.setattr(main, "CRITICAL_READINESS_CHECKS", (ReadinessCheck("database", explode),))

    async with AsyncClient(transport=ASGITransport(app=main.app), base_url="http://test") as client:
        response = await client.get("/health")

    assert response.status_code == 200


async def test_an_informational_dependency_that_is_down_still_answers_ready(monkeypatch, caplog):
    """A cache or broker outage must not take an instance out of rotation."""

    async def reachable() -> None:
        return None

    async def unreachable() -> None:
        raise ConnectionError("no route to host")

    monkeypatch.setattr(main, "CRITICAL_READINESS_CHECKS", (ReadinessCheck("database", reachable),))
    monkeypatch.setattr(main, "INFORMATIONAL_READINESS_CHECKS", (ReadinessCheck("cache", unreachable),))

    with caplog.at_level("WARNING"):
        async with AsyncClient(transport=ASGITransport(app=main.app), base_url="http://test") as client:
            response = await client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}
    assert "cache" in caplog.text


async def test_the_body_names_no_dependency(monkeypatch, caplog):
    """A public probe tells a load balancer whether to send traffic, and nothing else."""

    async def unreachable() -> None:
        raise ConnectionError("postgres://app:s3cret@db:5432 refused the connection")

    monkeypatch.setattr(main, "CRITICAL_READINESS_CHECKS", (ReadinessCheck("database", unreachable),))
    monkeypatch.setattr(main, "INFORMATIONAL_READINESS_CHECKS", (ReadinessCheck("cache", unreachable),))

    with caplog.at_level("WARNING"):
        async with AsyncClient(transport=ASGITransport(app=main.app), base_url="http://test") as client:
            response = await client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "not ready"}
    assert "database" not in response.text
    assert "cache" not in response.text
    assert "s3cret" not in response.text
    assert "database" in caplog.text
    assert "cache" in caplog.text
    assert "s3cret" not in caplog.text
