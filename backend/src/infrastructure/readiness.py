"""Running the readiness checks a project selected."""

import time
from collections.abc import Mapping, Sequence
from urllib.parse import urlsplit

import anyio

from .composition import ReadinessCheck
from .logging import get_logger

logger = get_logger()

CHECK_TIMEOUT_SECONDS = 2.0
REPORT_CACHE_SECONDS = 2.0

READY = "ready"
UNAVAILABLE = "unavailable"

DEFAULT_PORTS = {"redis": 6379, "rediss": 6379, "memcached": 11211}

_cached: dict[tuple[str, ...], tuple[float, dict[str, str]]] = {}
_in_flight: dict[tuple[str, ...], anyio.Event] = {}


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


def _key(checks: Sequence[ReadinessCheck]) -> tuple[str, ...]:
    """What identifies a report: the names of the checks it was taken for."""
    return tuple(check.name for check in checks)


def _remembered(key: tuple[str, ...]) -> dict[str, str] | None:
    """The report from the last probe of ``key``, while it is younger than ``REPORT_CACHE_SECONDS``."""
    entry = _cached.get(key)
    if entry is None or time.monotonic() - entry[0] >= REPORT_CACHE_SECONDS:
        return None

    return dict(entry[1])


async def _probe(checks: Sequence[ReadinessCheck]) -> tuple[dict[str, str], bool]:
    """The report, and whether the checks ran for it rather than it coming from the cache."""
    key = _key(checks)

    while True:
        remembered = _remembered(key)
        if remembered is not None:
            return remembered, False

        waiting = _in_flight.get(key)
        if waiting is None:
            break

        await waiting.wait()

    probing = anyio.Event()
    _in_flight[key] = probing

    try:
        report = await _run(checks)
        _cached[key] = (time.monotonic(), report)
    finally:
        del _in_flight[key]
        probing.set()

    return dict(report), True


def _server(check: ReadinessCheck) -> str | None:
    """The server ``check`` probes, as scheme, host and port, with whatever follows dropped."""
    if check.target is None:
        return None

    try:
        target = check.target()
    except Exception as error:
        logger.warning(f"Readiness check {check.name} could not name its server: {type(error).__name__}")
        return None

    if target is None:
        return None

    parsed = urlsplit(target)
    if parsed.hostname is None:
        return target

    port = parsed.port or DEFAULT_PORTS.get(parsed.scheme)

    return f"{parsed.scheme}://{parsed.hostname}:{port}"


async def _run(checks: Sequence[ReadinessCheck]) -> dict[str, str]:
    """Ask every check, together, asking one server once."""
    answers: dict[str, str] = {}
    asked: dict[str, str] = {}
    mirrors: dict[str, str] = {}

    async with anyio.create_task_group() as group:
        for check in checks:
            server = _server(check)
            if server is not None and server in asked:
                mirrors[check.name] = asked[server]
                continue

            if server is not None:
                asked[server] = check.name

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
    """Drop every remembered report; the next probe asks the checks again."""
    _cached.clear()
