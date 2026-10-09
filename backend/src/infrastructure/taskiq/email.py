"""Delivering the account emails from a worker, so the request doesn't wait on it."""

from typing import cast

from crudauth import EmailContext, EmailSender
from crudauth.email.constants import EmailKind

from ..email.factory import build_sender
from .brokers import default_broker

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
    """Puts the message on the task queue, where a worker delivers it."""

    async def send(self, *, to: str, subject: str, body: str, kind: EmailKind, context: EmailContext) -> None:
        """Enqueue one message, with the parts of ``context`` a worker needs to render it."""
        await send_email.kiq(
            to=to,
            subject=subject,
            body=body,
            kind=kind,
            link=context.link,
            expires_in=context.expires_in,
        )


queued_sender = QueuedSender()
