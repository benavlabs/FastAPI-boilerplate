"""Seeding the default tier, run as its own script."""

import logging

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import scripts.create_first_tier as script
from src.infrastructure.config.settings import settings
from src.modules.tier.models import Tier
from tests.unit.scripts.seed_helpers import no_cached_engine, run_script, script_environment

pytestmark = pytest.mark.asyncio


def _environment(database_url: str) -> dict[str, str]:
    """The script environment, carrying the DEFAULT_TIER_NAME the settings report."""
    return script_environment(database_url, DEFAULT_TIER_NAME=settings.DEFAULT_TIER_NAME)


async def test_the_script_seeds_the_default_tier(test_db_url: str, test_db_engine, db_session: AsyncSession):
    """``python scripts/create_first_tier.py``, with no app to import the models for it."""
    completed = run_script("create_first_tier", _environment(test_db_url))

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "Traceback" not in completed.stderr
    await db_session.rollback()
    seeded = await db_session.execute(select(Tier).where(Tier.name == settings.DEFAULT_TIER_NAME))
    assert seeded.scalar_one_or_none() is not None


async def test_a_database_it_cannot_reach_reports_one_line(test_db_url: str):
    environment = _environment(test_db_url)
    environment["POSTGRES_SERVER"] = "localhost"
    environment["POSTGRES_PORT"] = "1"

    completed = run_script("create_first_tier", environment)

    assert completed.returncode == 1
    assert "Traceback" not in completed.stderr
    assert "Could not seed the tier" in completed.stdout + completed.stderr


async def test_main_exits_one_when_the_database_is_down(monkeypatch, caplog):
    caplog.set_level(logging.ERROR)
    monkeypatch.setattr(settings, "POSTGRES_SERVER", "localhost")
    monkeypatch.setattr(settings, "POSTGRES_PORT", 1)

    with no_cached_engine(), pytest.raises(SystemExit) as exit_code:
        await script.main()

    assert exit_code.value.code == 1
    assert "Traceback" not in caplog.text
    assert "Could not seed the tier" in caplog.text
