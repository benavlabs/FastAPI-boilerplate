"""The panel's login lockout, in a key space the public login API cannot reach.

crudauth keys the per-identifier half of its lockout on whatever string arrives as a
username, so a lockout sharing the API's backend is writable by anybody: submitting
``admin-panel:<address>`` to ``POST /auth/login`` locked an operator out of the panel.
A backend of its own, under a prefix of its own, is what keeps the two apart; the
thresholds stay the ones the login uses, so the panel is no more forgiving than it was.
"""

from crudauth.ratelimit import LockoutPolicy

from ...infrastructure.auth.limiter import build_rate_limiter
from ...infrastructure.config.settings import settings

KEY_PREFIX = "admin-panel:rl:"
"""Put before every counter the panel writes, which nothing else writes under."""


def build_panel_lockout() -> LockoutPolicy | None:
    """The panel's own policy, or ``None`` where no limiter backend is configured."""
    backend = build_rate_limiter(prefix=KEY_PREFIX)
    if backend is None:
        return None

    return LockoutPolicy(
        backend,
        max_attempts=settings.LOGIN_MAX_ATTEMPTS,
        attempt_window_seconds=settings.LOGIN_ATTEMPT_WINDOW_SECONDS,
        lockout_base_seconds=settings.LOGIN_LOCKOUT_BASE_SECONDS,
        lockout_max_seconds=settings.LOGIN_LOCKOUT_MAX_SECONDS,
    )


panel_lockout = build_panel_lockout()
