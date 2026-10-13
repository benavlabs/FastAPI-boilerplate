"""The panel's login lockouts, in a key space the public login API cannot reach.

crudauth keys the per-identifier half of its lockout on whatever string arrives as a
username, so a lockout sharing the API's backend is writable by anybody: submitting
``admin-panel:<address>`` to ``POST /auth/login`` locked an operator out of the panel.
A backend of its own, under a prefix of its own, is what keeps the two apart; the
thresholds stay the ones the login uses, so the panel is no more forgiving than it was.

There are two policies. One counts an address against the login's own thresholds. The
other counts every failure the panel refuses, whatever address it came from, against
``ADDRESS_BUDGETS`` times the per-address cap: the panel has a single password, so an
attacker changing address would otherwise guess at it without limit.
"""

from crudauth.ratelimit import LockoutPolicy

from ...infrastructure.auth.limiter import build_rate_limiter
from ...infrastructure.config.settings import settings

KEY_PREFIX = "admin-panel:rl:"
"""Put before every counter the panel writes for one address, which nothing else writes under."""

EVERY_ADDRESS_KEY_PREFIX = "admin-panel:rl:all:"
"""Put before the counters every panel failure lands in, whatever address sent it."""

ADDRESS_BUDGETS = 5
"""How many per-address budgets all addresses together spend before the panel closes to them all."""


def _panel_policy(prefix: str, max_attempts: int) -> LockoutPolicy | None:
    """A policy over a backend of the panel's own, or ``None`` where none is configured."""
    backend = build_rate_limiter(prefix=prefix)
    if backend is None:
        return None

    return LockoutPolicy(
        backend,
        max_attempts=max_attempts,
        attempt_window_seconds=settings.LOGIN_ATTEMPT_WINDOW_SECONDS,
        lockout_base_seconds=settings.LOGIN_LOCKOUT_BASE_SECONDS,
        lockout_max_seconds=settings.LOGIN_LOCKOUT_MAX_SECONDS,
    )


def build_panel_lockout() -> LockoutPolicy | None:
    """The policy that counts one address's failures at the panel."""
    return _panel_policy(KEY_PREFIX, settings.LOGIN_MAX_ATTEMPTS)


def build_every_address_lockout() -> LockoutPolicy | None:
    """The policy that counts the panel's failures together, however many addresses sent them."""
    return _panel_policy(EVERY_ADDRESS_KEY_PREFIX, settings.LOGIN_MAX_ATTEMPTS * ADDRESS_BUDGETS)


panel_lockout = build_panel_lockout()
every_address_lockout = build_every_address_lockout()
