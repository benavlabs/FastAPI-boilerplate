"""Delivering the account emails from a worker, so the request doesn't wait on it."""

from typing import cast

import anyio
from crudauth import EmailContext, EmailSender
from crudauth.email.constants import EmailKind
from cryptography.fernet import InvalidToken

from ..email.factory import build_sender
from ..logging import get_logger
from .brokers import default_broker
from .constants import BROKER_CONNECT_SECONDS
from .sealing import seal, unseal

logger = get_logger()

EMAIL_TASK_NAME = "email:send"

sender = build_sender()
"""The sender the worker delivers through, built where a misconfigured backend fails the import."""


@default_broker.task(task_name=EMAIL_TASK_NAME, retry_on_error=True)
async def send_email(sealed: str, expires_in: int) -> None:
    """Deliver the one message ``sealed`` holds, through the sender ``EMAIL_BACKEND`` names.

    The message arrives sealed because a queue is not the place for a recovery link: the
    body carries one, and whoever can read the queue, or a backup of it, would read every
    link waiting in it.

    ``expires_in`` rides along unsealed, because the seal is opened against it: a message
    that waited longer than the link it carries lives is one nobody can use, and delivering
    it would send somebody a page that says only that the link has expired. At ``0`` the
    message names no lifetime and is opened however long it waited.

    A message this worker cannot open is logged and dropped rather than attempted again:
    neither a key that has changed nor a link that has run out is something a retry fixes.
    Nothing of the message is logged, since whatever is in there was sealed for a reason.
    """
    try:
        message = unseal(sealed, within=expires_in or None)
    except InvalidToken:
        logger.error(
            f"Could not open a sealed {EMAIL_TASK_NAME} message: SECRET_KEY has changed under it, or it "
            f"waited longer than the {expires_in}s the link it carries lives"
        )

        return

    message_kind = cast("EmailKind", message["kind"])
    recipient = message["to"]
    context = EmailContext(kind=message_kind, link=message["link"], recipient=recipient, expires_in=expires_in)

    await sender.send(to=recipient, subject=message["subject"], body=message["body"], kind=message_kind, context=context)


class QueuedSender(EmailSender):
    """Puts the message on the task queue, sealed, where a worker delivers it.

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
                    sealed=seal(
                        {
                            "to": to,
                            "subject": subject,
                            "body": body,
                            "kind": kind,
                            "link": context.link,
                        }
                    ),
                    expires_in=context.expires_in,
                )
        except Exception:
            logger.warning(f"Could not enqueue a {kind} email, delivering it in the request instead", exc_info=True)
            await sender.send(to=to, subject=subject, body=body, kind=kind, context=context)


queued_sender = QueuedSender()
