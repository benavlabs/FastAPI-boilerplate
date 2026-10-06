"""What each sender does with a message crudauth composed."""

import logging
import ssl
import warnings
from typing import Any

import httpx
import pytest
from crudauth import EmailContext, EmailSender
from testcontainers.mailpit import MailpitContainer

from src.infrastructure.email.senders import ConsoleSender, SmtpSender
from tests.conftest import is_docker_running

RECIPIENT = "owner@example.com"
SUBJECT = "Reset your password"
LINK = "https://app.example.com/reset-password?token=the-signed-token"
BODY = f"Someone asked to reset your password. Use this link: {LINK}"


async def _send_the_reset_email(sender: EmailSender) -> None:
    """One message, as crudauth hands it over."""
    await sender.send(
        to=RECIPIENT,
        subject=SUBJECT,
        body=BODY,
        kind="reset_password",
        context=EmailContext(kind="reset_password", link=LINK, recipient=RECIPIENT, expires_in=3600),
    )


@pytest.fixture(scope="module")
def mailpit():
    """A real SMTP server of this module's own, with an API to read what arrived."""
    if not is_docker_running():
        pytest.skip("Docker is required, but not running")

    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=DeprecationWarning, module="testcontainers.*")
        container = MailpitContainer().start()

    try:
        yield container
    finally:
        container.stop()


def _smtp_sender(mailpit: MailpitContainer, starttls: bool) -> SmtpSender:
    return SmtpSender(
        host=mailpit.get_container_host_ip(),
        port=mailpit.get_exposed_smtp_port(),
        sender="accounts@example.com",
        sender_name="Example Accounts",
        user="mailer",
        password="secret",
        starttls=starttls,
        timeout=10,
    )


def _delivered(mailpit: MailpitContainer) -> dict[str, Any]:
    """The one message Mailpit is holding, with its body."""
    api = mailpit.get_base_api_url()
    listed = httpx.get(f"{api}/api/v1/messages", timeout=10).json()["messages"]
    assert len(listed) == 1, listed
    message: dict[str, Any] = httpx.get(f"{api}/api/v1/message/{listed[0]['ID']}", timeout=10).json()

    return message


async def test_the_console_sender_logs_the_message(caplog):
    """Without a mail server there is nowhere to deliver, so the link goes to the log."""
    with caplog.at_level(logging.INFO):
        await _send_the_reset_email(ConsoleSender())

    assert RECIPIENT in caplog.text
    assert SUBJECT in caplog.text
    assert LINK in caplog.text


async def test_the_smtp_sender_delivers_the_message(mailpit: MailpitContainer):
    await _send_the_reset_email(_smtp_sender(mailpit, starttls=False))

    delivered = _delivered(mailpit)

    assert delivered["From"]["Address"] == "accounts@example.com"
    assert delivered["From"]["Name"] == "Example Accounts"
    assert [recipient["Address"] for recipient in delivered["To"]] == [RECIPIENT]
    assert delivered["Subject"] == SUBJECT
    assert LINK in delivered["Text"]


async def test_starttls_will_not_talk_to_a_server_it_cannot_verify(mailpit: MailpitContainer):
    """The container's certificate is self-signed, which is what a stranger's looks like."""
    with pytest.raises(ssl.SSLCertVerificationError):
        await _send_the_reset_email(_smtp_sender(mailpit, starttls=True))
