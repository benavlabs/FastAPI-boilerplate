"""The windows an API key's ``usage_limits`` may name, and the counters they become."""

from typing import Any

WINDOWS: dict[str, int] = {
    "requests_per_minute": 60,
    "requests_per_hour": 3600,
    "requests_per_day": 86400,
}
"""Each limit a key may carry, and the window in seconds it is counted over."""

COUNTER_PREFIX = "api_key"

REFUSALS_RECORDED_PER_WINDOW = 1
"""How many of the refusals a window answers are written as a usage row."""


def validated_limits(limits: dict[str, Any]) -> dict[str, int]:
    """``limits`` with every value read as a positive count of requests.

    Raises:
        ValueError: A name is not one of ``WINDOWS``, or a value is not a positive int.
    """
    unknown = sorted(set(limits) - set(WINDOWS))
    if unknown:
        raise ValueError(f"Unknown usage limit(s): {', '.join(unknown)}; use {', '.join(sorted(WINDOWS))}")

    for name, value in limits.items():
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            raise ValueError(f"{name} must be a positive number of requests, not {value!r}")

    return dict(limits)


def countable(limits: dict[str, Any]) -> dict[str, int]:
    """The windows in ``limits`` this project counts, with the rest left out.

    A write is validated, so only a limit stored before the vocabulary changed can name a
    window nothing counts. Such a limit counts for nothing, the way a stored permission
    the registry no longer knows grants nothing — never an error on every request the key
    makes.
    """
    return {
        name: value
        for name, value in limits.items()
        if name in WINDOWS and isinstance(value, int) and not isinstance(value, bool) and value >= 1
    }


def counted_shortest_first(limits: dict[str, Any]) -> list[tuple[str, int]]:
    """The windows in ``limits`` this project counts, the shortest window first.

    A request is counted against each of them in turn and refused by the first one it
    fills, so the order decides what a refusal costs: shortest first means a refusal
    leaves every longer window uncounted, and a key held at its per-minute limit keeps
    the rest of its day. The order the limits were written in is the client's, so it
    cannot be the one that is counted.
    """
    return sorted(countable(limits).items(), key=lambda counted: WINDOWS[counted[0]])


def counter_key(api_key_id: int, window: str) -> str:
    """The limiter key a key's window counts under."""
    return f"{COUNTER_PREFIX}:{api_key_id}:{window}"


def window_stamped(key: str, seconds: int, now: int) -> str:
    """``key`` as the limiter counts it, under the window of ``seconds`` running at ``now``.

    The limiter stamps a counter key with the window it belongs to, so each window is a key
    of its own that expires on its own. Stamping one here is how a window's count is read
    without counting a request against it.
    """
    return f"{key}:{now - now % seconds}"


def time_left(seconds: int, now: int) -> int:
    """How long until the window of ``seconds`` running at ``now`` rolls."""
    return seconds - now % seconds


def refusal_key(api_key_id: int, window: str) -> str:
    """The limiter key the refusals recorded for a window count under."""
    return f"{counter_key(api_key_id, window)}:refused"
