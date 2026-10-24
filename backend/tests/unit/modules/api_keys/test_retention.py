"""How long a key's usage rows are kept, and what the prune deletes."""

import logging
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError
from sqlalchemy import event, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Delete

from src.infrastructure.config.settings import settings
from src.infrastructure.database.session import Base
from src.modules.api_keys import retention
from src.modules.api_keys.models import APIKey, KeyUsage
from src.modules.api_keys.retention import ANALYTICS_MAX_DAYS, prune_key_usage, retained_days, retention_cutoff
from src.modules.api_keys.service import APIKeyService
from src.modules.api_keys.settings import APIKeySettings
from tests.unit.scripts.seed_helpers import run_script, script_environment

pytestmark = pytest.mark.asyncio

LAST_USED_AT = datetime(2026, 1, 2, 3, 4, tzinfo=UTC)
LAST_USED_IP = "203.0.113.7"


async def api_key_row(session: AsyncSession, user_id: int, name: str = "retained") -> int:
    """A key of ``user_id``'s, stamped as used, to hang usage rows off."""
    key = APIKey(
        user_id=user_id,
        name=name,
        key_hash=f"hash-{name}",
        key_prefix="bp_test",
        permissions=[],
        usage_limits={},
    )
    session.add(key)
    await session.flush()
    await session.execute(
        update(APIKey).where(APIKey.id == key.id).values(last_used_at=LAST_USED_AT, last_used_ip=LAST_USED_IP)
    )

    return key.id


async def usage_rows(session: AsyncSession, api_key_id: int, user_id: int, *ages: int) -> None:
    """One usage row per age, each written ``age`` days ago."""
    now = datetime.now(UTC)
    await session.execute(
        insert(KeyUsage),
        [
            {
                "api_key_id": api_key_id,
                "user_id": user_id,
                "endpoint": "/api/v1/widgets",
                "method": "GET",
                "status_code": 200,
                "cost_microcents": 10,
                "created_at": now - timedelta(days=age),
            }
            for age in ages
        ],
    )


async def row_ages(session: AsyncSession, api_key_id: int) -> list[int]:
    """How many whole days ago each surviving row was written, newest first."""
    written = await session.execute(select(KeyUsage.created_at).where(KeyUsage.api_key_id == api_key_id))
    now = datetime.now(UTC)

    return sorted((now - stamped).days for stamped in written.scalars())


class _Counting:
    """The statements the prune runs, so a test can count its batches."""

    def __init__(self, session: AsyncSession) -> None:
        self.deletes = 0
        self.commits = 0

        @event.listens_for(session.sync_session, "do_orm_execute")
        def executed(context) -> None:
            if isinstance(context.statement, Delete):
                self.deletes += 1

        @event.listens_for(session.sync_session, "after_commit")
        def committed(session) -> None:
            self.commits += 1

        self._handlers = (("do_orm_execute", executed), ("after_commit", committed))
        self._session = session

    def stop(self) -> None:
        for name, handler in self._handlers:
            event.remove(self._session.sync_session, name, handler)


@pytest.fixture
def counted(db_session: AsyncSession):
    """What the code under test asked the database to do."""
    counting = _Counting(db_session)

    yield counting

    counting.stop()


class TestWhatThePruneDeletes:
    """Rows past the cutoff go; the newer rows and the keys themselves stay."""

    async def test_a_row_past_the_cutoff_goes_and_a_newer_one_stays(self, db_session: AsyncSession, test_user: dict):
        key_id = await api_key_row(db_session, test_user["id"])
        await usage_rows(db_session, key_id, test_user["id"], 91, 89)

        pruned = await prune_key_usage(db_session, datetime.now(UTC) - timedelta(days=90))

        assert pruned == 1
        assert await row_ages(db_session, key_id) == [89]

    async def test_a_row_written_at_the_cutoff_stays(self, db_session: AsyncSession, test_user: dict):
        """The cutoff is the oldest moment kept, not the newest dropped."""
        key_id = await api_key_row(db_session, test_user["id"])
        cutoff = datetime.now(UTC) - timedelta(days=90)
        await db_session.execute(
            insert(KeyUsage),
            [
                {
                    "api_key_id": key_id,
                    "user_id": test_user["id"],
                    "endpoint": "/api/v1/widgets",
                    "method": "GET",
                    "status_code": 200,
                    "created_at": cutoff,
                }
            ],
        )

        assert await prune_key_usage(db_session, cutoff) == 0
        assert len(await row_ages(db_session, key_id)) == 1

    async def test_the_key_keeps_what_it_records_about_its_last_use(self, db_session: AsyncSession, test_user: dict):
        """A pruned key has no rows left, and still says when and from where it was used."""
        key_id = await api_key_row(db_session, test_user["id"])
        await usage_rows(db_session, key_id, test_user["id"], 400, 300)

        await prune_key_usage(db_session, datetime.now(UTC) - timedelta(days=90))

        stamped = (await db_session.execute(select(APIKey.last_used_at, APIKey.last_used_ip).where(APIKey.id == key_id))).one()
        assert stamped.last_used_at == LAST_USED_AT
        assert stamped.last_used_ip == LAST_USED_IP

    async def test_every_account_s_rows_are_pruned(self, db_session: AsyncSession, test_user: dict, test_user_2: dict):
        """The cutoff is the only thing the prune reads, so it has to reach every owner's rows."""
        theirs = await api_key_row(db_session, test_user_2["id"], "theirs")
        await usage_rows(db_session, theirs, test_user_2["id"], 91)

        assert await prune_key_usage(db_session, datetime.now(UTC) - timedelta(days=90)) == 1
        assert await row_ages(db_session, theirs) == []

    async def test_it_says_how_many_rows_it_deleted(self, db_session: AsyncSession, test_user: dict, caplog):
        key_id = await api_key_row(db_session, test_user["id"])
        await usage_rows(db_session, key_id, test_user["id"], 91, 92)

        with caplog.at_level(logging.INFO):
            await prune_key_usage(db_session, datetime.now(UTC) - timedelta(days=90))

        assert "Pruned 2 API key usage rows" in caplog.text


class TestThePruneInBatches:
    """A table left for months is deleted a batch at a time, not in one statement."""

    async def test_five_rows_take_three_batches_of_two(self, db_session: AsyncSession, test_user: dict, counted, monkeypatch):
        monkeypatch.setattr(retention, "PRUNE_BATCH_SIZE", 2)
        key_id = await api_key_row(db_session, test_user["id"])
        await usage_rows(db_session, key_id, test_user["id"], 91, 92, 93, 94, 95)

        pruned = await prune_key_usage(db_session, datetime.now(UTC) - timedelta(days=90))

        assert pruned == 5
        assert counted.deletes == 3
        assert counted.commits == 3
        assert await row_ages(db_session, key_id) == []

    async def test_a_table_with_nothing_to_prune_runs_one_statement(self, db_session: AsyncSession, test_user: dict, counted):
        key_id = await api_key_row(db_session, test_user["id"])
        await usage_rows(db_session, key_id, test_user["id"], 1)

        assert await prune_key_usage(db_session, datetime.now(UTC) - timedelta(days=90)) == 0
        assert (counted.deletes, counted.commits) == (0, 0)


class TestTheRetentionSetting:
    """``KEY_USAGE_RETENTION_DAYS`` says what to keep, and 0 keeps everything."""

    async def test_the_cutoff_is_the_retention_back_from_now(self, monkeypatch):
        monkeypatch.setattr(settings, "KEY_USAGE_RETENTION_DAYS", 30)

        cutoff = retention_cutoff()

        assert cutoff is not None
        assert 29 <= (datetime.now(UTC) - cutoff).days <= 30

    async def test_a_retention_of_zero_names_no_cutoff(self, monkeypatch):
        monkeypatch.setattr(settings, "KEY_USAGE_RETENTION_DAYS", 0)

        assert retention_cutoff() is None

    async def test_a_negative_retention_is_refused_as_the_settings_load(self, monkeypatch):
        """A typo would otherwise read as the 0 that keeps every row."""
        monkeypatch.setenv("KEY_USAGE_RETENTION_DAYS", "-90")

        with pytest.raises(ValidationError, match="KEY_USAGE_RETENTION_DAYS"):
            APIKeySettings()

    async def test_the_default_keeps_ninety_days(self):
        """A row carries an address and a user agent per request, so the default is a window."""
        assert settings.KEY_USAGE_RETENTION_DAYS == 90

    @pytest.mark.parametrize(
        ("retained", "reaches"), [(30, 30), (0, ANALYTICS_MAX_DAYS), (500, ANALYTICS_MAX_DAYS), (365, 365)]
    )
    async def test_how_far_back_the_rows_reach(self, monkeypatch, retained: int, reaches: int):
        monkeypatch.setattr(settings, "KEY_USAGE_RETENTION_DAYS", retained)

        assert retained_days() == reaches


class TestTheWindowTheAnalyticsRead:
    """Nobody is answered over a window the table no longer holds."""

    async def test_a_year_asked_for_reads_the_retention(self, db_session: AsyncSession, test_user: dict, monkeypatch):
        monkeypatch.setattr(settings, "KEY_USAGE_RETENTION_DAYS", 30)
        key_id = await api_key_row(db_session, test_user["id"])
        await usage_rows(db_session, key_id, test_user["id"], 100, 10)

        analytics = await APIKeyService().get_usage_analytics(key_id=key_id, user_id=test_user["id"], db=db_session, days=365)

        assert analytics["total_requests"] == 1

    async def test_a_window_inside_the_retention_is_read_as_asked(self, db_session: AsyncSession, test_user: dict, monkeypatch):
        monkeypatch.setattr(settings, "KEY_USAGE_RETENTION_DAYS", 90)
        key_id = await api_key_row(db_session, test_user["id"])
        await usage_rows(db_session, key_id, test_user["id"], 40, 10)

        analytics = await APIKeyService().get_usage_analytics(key_id=key_id, user_id=test_user["id"], db=db_session, days=30)

        assert analytics["total_requests"] == 1

    async def test_everything_kept_reads_the_year_asked_for(self, db_session: AsyncSession, test_user: dict, monkeypatch):
        monkeypatch.setattr(settings, "KEY_USAGE_RETENTION_DAYS", 0)
        key_id = await api_key_row(db_session, test_user["id"])
        await usage_rows(db_session, key_id, test_user["id"], 100)

        analytics = await APIKeyService().get_usage_analytics(key_id=key_id, user_id=test_user["id"], db=db_session, days=365)

        assert analytics["total_requests"] == 1


async def test_the_cutoff_has_an_index_to_read_it_from():
    """The other indexes lead with a key or a user, which a cutoff on its own cannot use."""
    usage_table = Base.metadata.tables["key_usage"]
    created = [
        index
        for index in usage_table.indexes
        if [column.name for column in index.expressions if hasattr(column, "name")] == ["created_at"]
    ]

    assert [index.name for index in created] == ["idx_key_usage_created"]


class TestTheScriptRunOnItsOwn:
    """``python scripts/prune_key_usage.py``, for a project with no worker to schedule it."""

    async def test_it_prunes_what_the_retention_leaves_behind(
        self, test_db_url: str, test_db_engine, db_session: AsyncSession, test_user: dict
    ):
        key_id = await api_key_row(db_session, test_user["id"])
        await usage_rows(db_session, key_id, test_user["id"], 91, 1)
        await db_session.commit()

        completed = run_script("prune_key_usage", script_environment(test_db_url, KEY_USAGE_RETENTION_DAYS="90"))

        assert completed.returncode == 0, completed.stdout + completed.stderr
        assert "Pruned 1 API key usage rows" in completed.stdout + completed.stderr
        await db_session.rollback()
        assert await row_ages(db_session, key_id) == [1]

    async def test_it_says_nothing_is_configured_to_prune_where_every_row_is_kept(
        self, test_db_url: str, test_db_engine, db_session: AsyncSession, test_user: dict
    ):
        key_id = await api_key_row(db_session, test_user["id"])
        await usage_rows(db_session, key_id, test_user["id"], 400)
        await db_session.commit()

        completed = run_script("prune_key_usage", script_environment(test_db_url, KEY_USAGE_RETENTION_DAYS="0"))

        assert completed.returncode == 0, completed.stdout + completed.stderr
        assert "nothing is configured to prune" in completed.stdout + completed.stderr
        await db_session.rollback()
        assert await row_ages(db_session, key_id) == [400]

    async def test_a_database_it_cannot_reach_fails_the_run(self, test_db_url: str):
        environment = script_environment(test_db_url, POSTGRES_SERVER="localhost", POSTGRES_PORT="1")

        completed = run_script("prune_key_usage", environment)

        assert completed.returncode == 1
        assert "Could not prune the usage rows" in completed.stdout + completed.stderr
