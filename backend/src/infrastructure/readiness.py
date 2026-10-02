"""Running the readiness checks a project selected."""

import time
from collections.abc import Mapping, Sequence

import anyio

from .composition import ReadinessCheck
from .logging import get_logger

logger = get_logger()

CHECK_TIMEOUT_SECONDS = 2.0
REPORT_CACHE_SECONDS = 2.0

READY = "ready"
UNAVAILABLE = "unavailable"

_cached: tuple[float, dict[str, str]] | None = None
_in_flight: anyio.Event | None = None


async def _ask(check: ReadinessCheck, answers: dict[str, str]) -> None:
    try:
        with anyio.fail_after(CHECK_TIMEOUT_SECONDS):
            await check.check()
    except TimeoutError:
        logger.warning(f"Readiness check {check.name} timed out")
        answers[check.name] = UNAVAILABLE
    except Exception as error:
        logger.warning(f"Readiness check {check.name} failed: {type(error).__name__}")
        answers[check.name] = UNAVAILABLE
    else:
        answers[check.name] = READY


async def probe(checks: Sequence[ReadinessCheck]) -> dict[str, str]:
    """What every check answers, one line per check, in the order the wiring lists them.

    The checks run together, each bounded by its own timeout; two checks pointed at one
    server are asked once; one probe runs at a time, with the rest awaiting its report;
    and that report is reused for ``REPORT_CACHE_SECONDS``.
    """
    report, _ = await _probe(checks)

    return report


def _remembered() -> dict[str, str] | None:
    """The report from the last probe, while it is younger than ``REPORT_CACHE_SECONDS``."""
    if _cached is None or time.monotonic() - _cached[0] >= REPORT_CACHE_SECONDS:
        return None

    return dict(_cached[1])


async def _probe(checks: Sequence[ReadinessCheck]) -> tuple[dict[str, str], bool]:
    """The report, and whether the checks ran for it rather than it coming from the cache."""
    global _cached, _in_flight

    while True:
        remembered = _remembered()
        if remembered is not None:
            return remembered, False

        if _in_flight is None:
            break

        await _in_flight.wait()

    _in_flight = anyio.Event()
    probing = _in_flight

    try:
        report = await _run(checks)
        _cached = (time.monotonic(), report)
    finally:
        _in_flight = None
        probing.set()

    return dict(report), True


async def _run(checks: Sequence[ReadinessCheck]) -> dict[str, str]:
    """Ask every check, together, asking one server once."""
    answers: dict[str, str] = {}
    asked: dict[str, str] = {}
    mirrors: dict[str, str] = {}

    async with anyio.create_task_group() as group:
        for check in checks:
            target = check.target() if check.target is not None else None
            if target is not None and target in asked:
                mirrors[check.name] = asked[target]
                continue

            if target is not None:
                asked[target] = check.name

            group.start_soon(_ask, check, answers)

    for name, source in mirrors.items():
        answers[name] = answers[source]

    return {check.name: answers[check.name] for check in checks}


async def readiness_report(critical: Sequence[ReadinessCheck], informational: Sequence[ReadinessCheck]) -> bool:
    """Whether every critical dependency answered ready.

    Which dependency answered what goes to the log, and only the probe that ran the
    checks writes those lines. An unavailable informational dependency leaves the
    answer ``True``.
    """
    answers, probed = await _probe((*critical, *informational))
    held_back = _unavailable(answers, critical)
    reported = _unavailable(answers, informational)

    if probed and reported:
        logger.warning(f"Readiness: {', '.join(reported)} unavailable, which does not hold traffic back")
    if probed and held_back:
        logger.error(f"Readiness: {', '.join(held_back)} unavailable, holding traffic back")

    return not held_back


def _unavailable(answers: Mapping[str, str], checks: Sequence[ReadinessCheck]) -> list[str]:
    """The names among ``checks`` that did not answer ready."""
    return [check.name for check in checks if answers.get(check.name) != READY]


def forget_cached_report() -> None:
    """Drop the remembered report; the next probe asks the checks again."""
    global _cached
    _cached = None
