"""Running the readiness checks: bounded, concurrent, deduplicated and briefly remembered."""

import anyio
import pytest

from src.infrastructure import readiness as readiness_module
from src.infrastructure.composition import ReadinessCheck
from src.infrastructure.readiness import READY, UNAVAILABLE, forget_cached_report, probe, readiness_report

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def forget_between_tests():
    forget_cached_report()
    yield
    forget_cached_report()


async def _collect(checks, reports: list[dict[str, str]]) -> None:
    """Probe and keep the report, for tests that probe from several tasks at once."""
    reports.append(await probe(checks))


def _answering(name: str, *, calls: list[str], fails: bool = False, target: str | None = None) -> ReadinessCheck:
    async def check() -> None:
        calls.append(name)
        if fails:
            raise ConnectionRefusedError("nothing listening")

    return ReadinessCheck(name, check, target=(lambda: target) if target else None)


async def test_every_check_is_reported_in_wiring_order():
    calls: list[str] = []
    checks = (_answering("database", calls=calls), _answering("cache", calls=calls, fails=True))

    report = await probe(checks)

    assert list(report) == ["database", "cache"]
    assert report == {"database": READY, "cache": UNAVAILABLE}


async def test_a_check_that_hangs_is_reported_unavailable(monkeypatch):
    monkeypatch.setattr(readiness_module, "CHECK_TIMEOUT_SECONDS", 0.05)

    async def hangs() -> None:
        await anyio.sleep(5)

    report = await probe((ReadinessCheck("database", hangs),))

    assert report == {"database": UNAVAILABLE}


async def test_the_checks_run_together():
    """One slow dependency must not add its wait to every other check."""
    started = anyio.Event()

    async def first() -> None:
        started.set()
        await anyio.sleep(0.05)

    async def second() -> None:
        with anyio.fail_after(1):
            await started.wait()

    report = await probe((ReadinessCheck("first", first), ReadinessCheck("second", second)))

    assert report == {"first": READY, "second": READY}


async def test_a_shared_server_that_is_down_marks_both_checks():
    calls: list[str] = []
    checks = (
        _answering("cache", calls=calls, fails=True, target="redis://redis:6379/0"),
        _answering("sessions", calls=calls, fails=True, target="redis://redis:6379/0"),
    )

    report = await probe(checks)

    assert calls == ["cache"]
    assert report == {"cache": UNAVAILABLE, "sessions": UNAVAILABLE}


async def test_a_flood_of_probes_asks_once():
    """The report is remembered briefly, so probes can't take the pool from real requests."""
    calls: list[str] = []
    checks = (_answering("database", calls=calls),)

    for _ in range(20):
        await probe(checks)

    assert calls == ["database"]


async def test_the_remembered_report_expires(monkeypatch):
    monkeypatch.setattr(readiness_module, "REPORT_CACHE_SECONDS", 0.0)
    calls: list[str] = []
    checks = (_answering("database", calls=calls),)

    await probe(checks)
    await probe(checks)

    assert calls == ["database", "database"]


async def test_a_failure_logs_the_name_and_the_exception_type_only(caplog):
    """A driver can put connection details in its message; the name and type are enough."""

    async def fails() -> None:
        raise ConnectionRefusedError("connecting to postgres://app:s3cret@db:5432 failed")

    with caplog.at_level("WARNING"):
        await probe((ReadinessCheck("database", fails),))

    assert "ConnectionRefusedError" in caplog.text
    assert "s3cret" not in caplog.text


class TestWhichChecksGateTraffic:
    """A critical dependency decides the answer; an informational one is only reported."""

    async def test_an_informational_failure_leaves_the_app_ready(self, caplog):
        calls: list[str] = []
        critical = (_answering("database", calls=calls),)
        informational = (_answering("cache", calls=calls, fails=True),)

        with caplog.at_level("WARNING"):
            ready = await readiness_report(critical, informational)

        assert ready is True
        assert "cache unavailable, which does not hold traffic back" in caplog.text

    async def test_a_critical_failure_holds_traffic_back(self, caplog):
        calls: list[str] = []
        critical = (_answering("database", calls=calls, fails=True),)
        informational = (_answering("cache", calls=calls),)

        with caplog.at_level("WARNING"):
            ready = await readiness_report(critical, informational)

        assert ready is False
        assert "database unavailable, holding traffic back" in caplog.text

    async def test_everything_reachable_is_ready(self):
        calls: list[str] = []

        ready = await readiness_report((_answering("database", calls=calls),), (_answering("cache", calls=calls),))

        assert ready is True
        assert calls == ["database", "cache"]

    async def test_the_informational_warning_is_logged_once_per_probe(self, caplog):
        """A probe answered from the remembered report logs nothing of its own."""
        calls: list[str] = []
        critical = (_answering("database", calls=calls),)
        informational = (_answering("cache", calls=calls, fails=True),)

        with caplog.at_level("WARNING"):
            assert await readiness_report(critical, informational) is True
            assert await readiness_report(critical, informational) is True

        assert calls == ["database", "cache"]
        assert caplog.text.count("which does not hold traffic back") == 1


class TestOneProbeAtATime:
    """Probes that arrive together share the one check, and the slow one isn't repeated."""

    async def test_fifty_probes_at_once_ask_once(self):
        calls: list[str] = []

        async def slow() -> None:
            calls.append("asked")
            await anyio.sleep(0.05)

        checks = (ReadinessCheck("database", slow),)
        reports: list[dict[str, str]] = []

        async with anyio.create_task_group() as group:
            for _ in range(50):
                group.start_soon(lambda: _collect(checks, reports))

        assert calls == ["asked"]
        assert reports == [{"database": READY}] * 50

    async def test_a_waiter_gets_the_answer_the_probe_found(self):
        async def slow_and_unreachable() -> None:
            await anyio.sleep(0.05)
            raise ConnectionRefusedError("nothing listening")

        checks = (ReadinessCheck("cache", slow_and_unreachable),)
        reports: list[dict[str, str]] = []

        async with anyio.create_task_group() as group:
            for _ in range(5):
                group.start_soon(lambda: _collect(checks, reports))

        assert reports == [{"cache": UNAVAILABLE}] * 5


class TestWhatCountsAsOneServer:
    """Two checks on one server are asked once, whatever they name after the port."""

    async def test_two_redis_databases_on_one_server_are_asked_once(self):
        calls: list[str] = []
        checks = (
            _answering("cache", calls=calls, target="redis://redis:6379/0"),
            _answering("sessions", calls=calls, target="redis://redis:6379/1"),
            _answering("broker", calls=calls, target="redis://redis:6379/3"),
        )

        report = await probe(checks)

        assert calls == ["cache"]
        assert report == {"cache": READY, "sessions": READY, "broker": READY}

    async def test_the_same_server_with_and_without_a_password_is_one_server(self):
        calls: list[str] = []
        checks = (
            _answering("cache", calls=calls, target="redis://:secret@redis:6379/0"),
            _answering("sessions", calls=calls, target="redis://redis:6379/1"),
        )

        report = await probe(checks)

        assert calls == ["cache"]
        assert report == {"cache": READY, "sessions": READY}

    async def test_a_url_without_a_port_is_the_same_server_as_one_with_the_default(self):
        calls: list[str] = []
        checks = (
            _answering("cache", calls=calls, target="redis://redis/0"),
            _answering("sessions", calls=calls, target="redis://redis:6379/1"),
            _answering("memcached", calls=calls, target="memcached://cache"),
            _answering("memcached_again", calls=calls, target="memcached://cache:11211"),
        )

        await probe(checks)

        assert calls == ["cache", "memcached"]

    async def test_targets_that_are_not_urls_are_matched_whole(self):
        calls: list[str] = []
        checks = (
            _answering("first", calls=calls, target="a-queue"),
            _answering("second", calls=calls, target="another-queue"),
            _answering("third", calls=calls, target="a-queue"),
        )

        await probe(checks)

        assert calls == ["first", "second"]

    async def test_different_servers_are_each_asked(self):
        calls: list[str] = []
        checks = (
            _answering("cache", calls=calls, target="redis://redis:6379/0"),
            _answering("sessions", calls=calls, target="redis://sessions:6379/0"),
            _answering("memcached", calls=calls, target="memcached://redis:11211"),
        )

        await probe(checks)

        assert calls == ["cache", "sessions", "memcached"]


class TestTheRememberedReportBelongsToItsChecks:
    """A report answers only for the checks it was taken for."""

    async def test_another_set_of_checks_is_asked_for_itself(self):
        calls: list[str] = []

        first = await probe((_answering("database", calls=calls),))
        second = await probe((_answering("cache", calls=calls),))

        assert first == {"database": READY}
        assert second == {"cache": READY}
        assert calls == ["database", "cache"]

    async def test_the_same_checks_are_remembered(self):
        calls: list[str] = []
        checks = (_answering("database", calls=calls),)

        await probe(checks)
        await probe(checks)

        assert calls == ["database"]


class TestATargetThatCannotBeNamed:
    """A check whose target raises is still asked, and nothing escapes the probe."""

    async def test_the_probe_still_answers(self, caplog):
        calls: list[str] = []

        def explode() -> str:
            raise ValueError("POSTGRES_DB cannot contain /")

        check = ReadinessCheck("database", _answering("database", calls=calls).check, target=explode)

        with caplog.at_level("WARNING"):
            report = await probe((check,))

        assert report == {"database": READY}
        assert calls == ["database"]
        assert "ValueError" in caplog.text
