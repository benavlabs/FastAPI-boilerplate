"""Delivering the account emails from a worker, so the request doesn't wait on it."""

from typing import cast

import anyio
from crudauth import EmailContext, EmailSender
from crudauth.email.constants import EmailKind

from ..email.factory import build_sender
from ..logging import get_logger
from .brokers import default_broker
from .constants import BROKER_CONNECT_SECONDS

logger = get_logger()

EMAIL_TASK_NAME = "email:send"

sender = build_sender()
"""The sender the worker delivers through, built where a misconfigured backend fails the import."""


@default_broker.task(task_name=EMAIL_TASK_NAME, retry_on_error=True)
async def send_email(to: str, subject: str, body: str, kind: str, link: str | None, expires_in: int) -> None:
    """Deliver one message through the sender ``EMAIL_BACKEND`` names."""
    message_kind = cast("EmailKind", kind)
    context = EmailContext(kind=message_kind, link=link, recipient=to, expires_in=expires_in)

    await sender.send(to=to, subject=subject, body=body, kind=message_kind, context=context)


class QueuedSender(EmailSender):
    """Puts the message on the task queue, where a worker delivers it.

    A broker that cannot be reached falls back to delivering in the request. Every account
    email is best-effort to the caller that asked for one: a failure is logged and the
    answer is the same either way, so there is nothing to retry and nobody to tell. An
    enqueue nobody catches loses the message, and a recovery link is the one piece of mail
    an account cannot do without.
    """

    async def send(self, *, to: str, subject: str, body: str, kind: EmailKind, context: EmailContext) -> None:
        """Enqueue one message, with the parts of ``context`` a worker needs to render it.

        Delivers it here instead where the queue will not take it, which costs the request
        what the delivery takes.

        The enqueue is given ``BROKER_CONNECT_SECONDS`` of its own, because a broker that
        refuses is not the slow case: one that accepts the connection and says nothing, or
        is reconnecting, would hold the request rather than reach the delivery below. A
        message that landed just as the time ran out is delivered as well as queued, and
        the account reads it twice. That is the trade: a duplicate beats a recovery link
        nobody is sent.
        """
        try:
            with anyio.fail_after(BROKER_CONNECT_SECONDS):
                await send_email.kiq(
                    to=to,
                    subject=subject,
                    body=body,
                    kind=kind,
                    link=context.link,
                    expires_in=context.expires_in,
                )
        except Exception:
            logger.warning(f"Could not enqueue a {kind} email, delivering it in the request instead", exc_info=True)
            await sender.send(to=to, subject=subject, body=body, kind=kind, context=context)


queued_sender = QueuedSender()
