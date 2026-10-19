"""The scheduled prune: when the scheduler fires it, and what one run does."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.config.settings import settings
from src.infrastructure.taskiq.brokers import default_broker
from src.infrastructure.taskiq.scheduler import scheduler
from src.modules.api_keys.tasks import PRUNE_CRON, PRUNE_TASK_NAME, prune_usage
from src.wiring.tasks import TASK_MODULES
from tests.unit.modules.api_keys.test_retention import api_key_row, row_ages, usage_rows

pytestmark = pytest.mark.asyncio


async def test_the_worker_registers_the_prune_under_its_own_name():
    """A task the worker doesn't know drops the message the scheduler enqueued."""
    assert "src.modules.api_keys.tasks" in TASK_MODULES
    assert default_broker.find_task(PRUNE_TASK_NAME) is not None


async def test_the_scheduler_fires_it_once_a_day():
    for source in scheduler.sources:
        await source.startup()

    found = [(task.task_name, task.cron) for source in scheduler.sources for task in await source.get_schedules()]

    assert (PRUNE_TASK_NAME, PRUNE_CRON) in found
    assert PRUNE_CRON == "0 3 * * *"


async def test_one_run_deletes_the_rows_past_the_retention(db_session: AsyncSession, test_user: dict, monkeypatch):
    monkeypatch.setattr(settings, "KEY_USAGE_RETENTION_DAYS", 90)
    key_id = await api_key_row(db_session, test_user["id"])
    await usage_rows(db_session, key_id, test_user["id"], 91, 2)

    assert await prune_usage.original_func(db=db_session) == 1
    assert await row_ages(db_session, key_id) == [2]


async def test_a_retention_of_zero_deletes_nothing(db_session: AsyncSession, test_user: dict, monkeypatch, caplog):
    monkeypatch.setattr(settings, "KEY_USAGE_RETENTION_DAYS", 0)
    key_id = await api_key_row(db_session, test_user["id"])
    await usage_rows(db_session, key_id, test_user["id"], 400)

    assert await prune_usage.original_func(db=db_session) == 0
    assert await row_ages(db_session, key_id) == [400]
    assert "every API key usage row is kept" in caplog.text


async def test_the_run_answers_how_many_rows_it_deleted(db_session: AsyncSession, test_user: dict, monkeypatch):
    """The result backend holds the count, so a scheduled run leaves a record of its size."""
    monkeypatch.setattr(settings, "KEY_USAGE_RETENTION_DAYS", 30)
    key_id = await api_key_row(db_session, test_user["id"])
    await usage_rows(db_session, key_id, test_user["id"], 31, 32, 33)

    assert await prune_usage.original_func(db=db_session) == 3
    assert await row_ages(db_session, key_id) == []


async def test_the_cutoff_it_prunes_from_is_the_configured_one(db_session: AsyncSession, test_user: dict, monkeypatch):
    """A row inside the retention survives a run that deletes the one just outside it."""
    monkeypatch.setattr(settings, "KEY_USAGE_RETENTION_DAYS", 7)
    key_id = await api_key_row(db_session, test_user["id"])
    await usage_rows(db_session, key_id, test_user["id"], 8, 6)
    newest = datetime.now(UTC) - timedelta(days=6)

    await prune_usage.original_func(db=db_session)

    assert await row_ages(db_session, key_id) == [(datetime.now(UTC) - newest).days]
