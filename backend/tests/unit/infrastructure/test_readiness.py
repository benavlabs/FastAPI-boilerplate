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


async def test_two_checks_on_one_server_are_asked_once():
    calls: list[str] = []
    checks = (
        _answering("cache", calls=calls, target="redis://redis:6379/0"),
        _answering("sessions", calls=calls, target="redis://redis:6379/0"),
        _answering("broker", calls=calls, target="redis://redis:6379/3"),
    )

    report = await probe(checks)

    assert calls == ["cache", "broker"]
    assert report == {"cache": READY, "sessions": READY, "broker": READY}


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
            ready, answers = await readiness_report(critical, informational)

        assert ready is True
        assert answers == {"database": READY, "cache": UNAVAILABLE}
        assert "cache" in caplog.text

    async def test_a_critical_failure_holds_traffic_back(self):
        calls: list[str] = []
        critical = (_answering("database", calls=calls, fails=True),)
        informational = (_answering("cache", calls=calls),)

        ready, answers = await readiness_report(critical, informational)

        assert ready is False
        assert answers == {"database": UNAVAILABLE, "cache": READY}

    async def test_everything_reachable_is_ready(self):
        calls: list[str] = []

        ready, answers = await readiness_report((_answering("database", calls=calls),), (_answering("cache", calls=calls),))

        assert ready is True
        assert answers == {"database": READY, "cache": READY}

    async def test_the_informational_warning_is_logged_once_per_probe(self, caplog):
        """A probe answered from the remembered report logs nothing of its own."""
        calls: list[str] = []
        critical = (_answering("database", calls=calls),)
        informational = (_answering("cache", calls=calls, fails=True),)

        with caplog.at_level("WARNING"):
            await readiness_report(critical, informational)
            await readiness_report(critical, informational)

        assert calls == ["database", "cache"]
        assert caplog.text.count("which does not hold traffic back") == 1
