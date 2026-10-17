"""The senders crudauth hands a composed message to."""

import smtplib
import ssl
from asyncio import to_thread
from email.headerregistry import Address
from email.message import EmailMessage

from crudauth import EmailContext, EmailSender
from crudauth.email.constants import EmailKind

from ..logging import get_logger

logger = get_logger()


class ConsoleSender(EmailSender):
    """Logs the message instead of delivering it."""

    async def send(self, *, to: str, subject: str, body: str, kind: EmailKind, context: EmailContext) -> None:
        """Log one message, link and all."""
        logger.info(f"Email not delivered ({kind}), logged instead. To: {to}. Subject: {subject}\n{body}")


class SmtpSender(EmailSender):
    """Delivers over SMTP, on a connection of its own per message."""

    def __init__(
        self,
        host: str,
        port: int,
        sender: str,
        sender_name: str = "",
        user: str = "",
        password: str = "",
        starttls: bool = True,
        timeout: int = 10,
    ) -> None:
        self.host = host
        self.port = port
        self.sender = sender
        self.sender_name = sender_name
        self.user = user
        self.password = password
        self.starttls = starttls
        self.timeout = timeout

    async def send(self, *, to: str, subject: str, body: str, kind: EmailKind, context: EmailContext) -> None:
        """Hand one message to the SMTP server, off the event loop."""
        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = self._from_header()
        message["To"] = to
        message.set_content(body)

        await to_thread(self._deliver, message)

    def _from_header(self) -> str | Address:
        if not self.sender_name:
            return self.sender

        username, _, domain = self.sender.partition("@")

        return Address(display_name=self.sender_name, username=username, domain=domain)

    def _deliver(self, message: EmailMessage) -> None:
        with smtplib.SMTP(self.host, self.port, timeout=self.timeout) as server:
            if self.starttls:
                server.starttls(context=ssl.create_default_context())
            if self.user:
                server.login(self.user, self.password)
            server.send_message(message)
