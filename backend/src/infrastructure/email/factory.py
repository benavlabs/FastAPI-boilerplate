"""Building the sender ``EMAIL_BACKEND`` names."""

from crudauth import EmailSender

from ..config.enums import EmailBackend
from ..config.settings import settings
from .senders import ConsoleSender, SmtpSender


def build_sender() -> EmailSender:
    """The sender this project's settings describe.

    Raises:
        ValueError: ``EMAIL_BACKEND`` names a backend this project has no sender for,
            or names ``smtp`` without a server to deliver to.
    """
    if settings.EMAIL_BACKEND == EmailBackend.CONSOLE.value:
        return ConsoleSender()

    if settings.EMAIL_BACKEND != EmailBackend.SMTP.value:
        raise ValueError(
            f"EMAIL_BACKEND is {settings.EMAIL_BACKEND!r}; this project sends over "
            f"{EmailBackend.CONSOLE.value} or {EmailBackend.SMTP.value}."
        )

    if not settings.EMAIL_SMTP_HOST:
        raise ValueError("EMAIL_BACKEND is 'smtp' but EMAIL_SMTP_HOST is empty: there is nothing to deliver to.")

    return SmtpSender(
        host=settings.EMAIL_SMTP_HOST,
        port=settings.EMAIL_SMTP_PORT,
        sender=settings.EMAIL_FROM,
        sender_name=settings.EMAIL_FROM_NAME,
        user=settings.EMAIL_SMTP_USER,
        password=settings.EMAIL_SMTP_PASSWORD,
        starttls=settings.EMAIL_SMTP_STARTTLS,
        timeout=settings.EMAIL_SMTP_TIMEOUT_SECONDS,
    )
