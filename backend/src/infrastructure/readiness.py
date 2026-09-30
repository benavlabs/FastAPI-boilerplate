"""Running the readiness checks a project selected."""

import time
from collections.abc import Sequence

import anyio

from .composition import ReadinessCheck
from .logging import get_logger

logger = get_logger()

CHECK_TIMEOUT_SECONDS = 2.0
REPORT_CACHE_SECONDS = 2.0

READY = "ready"
UNAVAILABLE = "unavailable"

_cached: tuple[float, dict[str, str]] | None = None


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

    The checks run together, each bounded by its own timeout, and two checks pointed
    at one server are asked once. The report is reused for a couple of seconds, so a
    flood of probes can't take the database pool away from real requests.
    """
    global _cached

    now = time.monotonic()
    if _cached is not None and now - _cached[0] < REPORT_CACHE_SECONDS:
        return dict(_cached[1])

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

    report = {check.name: answers[check.name] for check in checks}
    _cached = (time.monotonic(), report)

    return dict(report)


def forget_cached_report() -> None:
    """Drop the remembered report, so the next probe asks again."""
    global _cached
    _cached = None
