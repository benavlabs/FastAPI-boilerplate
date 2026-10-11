"""What a refused sign-in leaves behind: a log line per refusal and per lockout.

Registered as crudauth's ``on_login_failed`` and ``on_lockout`` hooks, so every path that
refuses a password login records the attempt.

An identifier is written out only where an account has it. What arrives in the username
field may be a typo, a probe, another account's address or a password typed one box too
high, and none of those belong in a log. The lockout line names no identifier: it refuses
the request before anything resolves one.
"""

from crudauth import HookContext

from ..logging import get_logger

logger = get_logger()

UNKNOWN_IDENTIFIER = "an identifier no account has"


def _where(context: HookContext) -> str:
    """The address the attempt came from, past the trusted proxies, and its user agent."""
    return f"{context.ip_address or 'an unknown address'} ({context.user_agent or 'no user agent'})"


async def record_a_refused_login(identifier: str, *, user: dict | None, reason: str, context: HookContext) -> None:
    """Log a refused password login: why, where from, and what was tried where an account has it."""
    tried = repr(identifier) if user is not None else UNKNOWN_IDENTIFIER
    logger.warning(f"login refused: {tried} from {_where(context)}; {reason}")


async def record_a_lockout(identifier: str, *, retry_after: int, context: HookContext) -> None:
    """Log the login lockout engaging: how long it refuses for, and where from."""
    logger.warning(f"login locked out for {retry_after}s, from {_where(context)}")
