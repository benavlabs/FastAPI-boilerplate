"""Ending an account's sessions where something it recovers with has changed."""

from collections.abc import Awaitable, Callable
from typing import Any

from crudauth import HookContext
from crudauth.transports.session.transport import SessionTransport
from sqlalchemy.ext.asyncio import AsyncSession

from ..logging import get_logger

logger = get_logger()


def end_every_session_through(transport: SessionTransport) -> Callable[..., Awaitable[None]]:
    """A hook that ends every session of the account whose address has just changed.

    The address is what recovers an account, so changing it is a credential change and is
    treated as one: a password reset already evicts an account's sessions. A session
    somebody else holds is what this ends; the owner is told by the notice to the old
    address either way.

    Every session goes, the one that asked for the change included, because the
    confirmation is a link clicked from the new mailbox and carries no session to keep. The
    owner signs in again, as their new address. API keys are untouched: they carry the
    generation they were minted under, and nothing about an address moves that.

    The manager is read when the hook runs rather than when it is built, since the
    transport is given one as ``CRUDAuth`` binds it.
    """

    async def ending_them(user: dict[str, Any], *, db: AsyncSession, context: HookContext) -> None:
        manager = transport.manager
        if manager is None:
            return

        account = user.get("id")
        ended = await manager.revoke_all(account)
        logger.info(f"Ended {ended} session(s) of account {account}, whose address changed")

    return ending_them
