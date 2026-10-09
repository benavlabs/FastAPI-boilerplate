"""The windows an API key's ``usage_limits`` may name, and the counters they become."""

from typing import Any

WINDOWS: dict[str, int] = {
    "requests_per_minute": 60,
    "requests_per_hour": 3600,
    "requests_per_day": 86400,
}
"""Each limit a key may carry, and the window in seconds it is counted over."""

COUNTER_PREFIX = "api_key"


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


def counter_key(api_key_id: int, window: str) -> str:
    """The limiter key a key's window counts under."""
    return f"{COUNTER_PREFIX}:{api_key_id}:{window}"
