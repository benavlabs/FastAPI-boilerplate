"""What a refused sign-in leaves behind: a log line per refusal and per lockout.

``record_a_refused_login`` and ``record_a_lockout`` are registered as crudauth's
``on_login_failed`` and ``on_lockout`` hooks, so every path that refuses a password login
records the attempt. ``log_a_refusal`` and ``log_a_lockout`` write the same two lines for
a door crudauth doesn't answer, such as the admin panel's own login.

An identifier is written out only where an account has it. What arrives in the username
field may be a typo, a probe, another account's address or a password typed one box too
high, and none of those belong in a log. A lockout line names no identifier: it refuses
the request before anything resolves one.
"""

from crudauth import HookContext

from ..logging import get_logger

logger = get_logger()

UNKNOWN_IDENTIFIER = "an identifier no account has"

LOGIN_API = "the login api"
"""The door crudauth's own routes answer, named in the lines its hooks write."""


def _where(context: HookContext) -> str:
    """The address the attempt came from, past the trusted proxies, and its user agent."""
    return f"{context.ip_address or 'an unknown address'} ({context.user_agent or 'no user agent'})"


async def log_a_refusal(door: str, identifier: str, *, known: bool, reason: str, context: HookContext) -> None:
    """Log a login refused at ``door``: why, where from, and what was tried where an account has it."""
    tried = repr(identifier) if known else UNKNOWN_IDENTIFIER
    logger.warning(f"login refused at {door}: {tried} from {_where(context)}; {reason}")


async def log_a_lockout(door: str, *, retry_after: int, context: HookContext) -> None:
    """Log ``door``'s lockout engaging: how long it refuses for, and where from."""
    logger.warning(f"login locked out at {door} for {retry_after}s, from {_where(context)}")


async def record_a_refused_login(identifier: str, *, user: dict | None, reason: str, context: HookContext) -> None:
    """Log a password login the login API refused."""
    await log_a_refusal(LOGIN_API, identifier, known=user is not None, reason=reason, context=context)


async def record_a_lockout(identifier: str, *, retry_after: int, context: HookContext) -> None:
    """Log the login API's lockout engaging."""
    await log_a_lockout(LOGIN_API, retry_after=retry_after, context=context)
