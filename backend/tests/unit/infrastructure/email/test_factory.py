"""Which sender the settings describe."""

import pytest

from src.infrastructure.config.settings import settings
from src.infrastructure.email import factory
from src.infrastructure.email.senders import ConsoleSender, SmtpSender


@pytest.fixture
def configured(monkeypatch):
    """The email settings, as a project's environment would leave them."""

    def with_settings(**values: object):
        for name, value in values.items():
            monkeypatch.setattr(settings, name, value)

        return factory.build_sender

    return with_settings


def test_a_project_that_configured_nothing_logs_its_emails(configured):
    """The default has to work without a mail server, and without sending anything."""
    assert isinstance(configured()(), ConsoleSender)


def test_the_smtp_backend_is_built_from_the_settings(configured):
    build = configured(
        EMAIL_BACKEND="smtp",
        EMAIL_SMTP_HOST="mail.example.com",
        EMAIL_SMTP_PORT=2525,
        EMAIL_FROM="accounts@example.com",
        EMAIL_FROM_NAME="Example",
        EMAIL_SMTP_USER="mailer",
        EMAIL_SMTP_PASSWORD="secret",
        EMAIL_SMTP_STARTTLS=False,
        EMAIL_SMTP_TIMEOUT_SECONDS=3,
    )

    sender = build()

    assert isinstance(sender, SmtpSender)
    assert (sender.host, sender.port, sender.timeout) == ("mail.example.com", 2525, 3)
    assert (sender.sender, sender.sender_name) == ("accounts@example.com", "Example")
    assert (sender.user, sender.password, sender.starttls) == ("mailer", "secret", False)


def test_the_smtp_backend_without_a_server_is_refused(configured):
    build = configured(EMAIL_BACKEND="smtp", EMAIL_SMTP_HOST="")

    with pytest.raises(ValueError, match="EMAIL_SMTP_HOST"):
        build()


def test_a_backend_this_project_cannot_send_over_is_refused(configured):
    build = configured(EMAIL_BACKEND="postmark")

    with pytest.raises(ValueError, match="postmark"):
        build()
