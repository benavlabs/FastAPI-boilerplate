"""Handing an account email to the worker, and what arrives there."""

import os
import subprocess
import sys
from pathlib import Path

from crudauth import EmailContext, EmailSender
from crudauth.email.constants import EmailKind
from taskiq import InMemoryBroker

from src.infrastructure.taskiq import email as taskiq_email
from src.infrastructure.taskiq.email import EMAIL_TASK_NAME, queued_sender, send_email

RECIPIENT = "owner@example.com"
SUBJECT = "Confirm your email"
LINK = "https://app.example.com/verify-email?token=the-signed-token"
BODY = f"Confirm your address: {LINK}"
CONTEXT = EmailContext(kind="verify_email", link=LINK, recipient=RECIPIENT, expires_in=7200)
BACKEND = Path(__file__).resolve().parents[4]

_IMPORT_THE_SENDER = """
from src.infrastructure.taskiq.email import queued_sender

print("IMPORTED")
"""


class _Capturing(EmailSender):
    """The sender the worker ends up delivering through."""

    def __init__(self) -> None:
        self.sent: list[dict[str, object]] = []

    async def send(self, *, to: str, subject: str, body: str, kind: EmailKind, context: EmailContext) -> None:
        self.sent.append({"to": to, "subject": subject, "body": body, "kind": kind, "context": context})


async def _enqueue_the_verification_email() -> None:
    await queued_sender.send(to=RECIPIENT, subject=SUBJECT, body=BODY, kind="verify_email", context=CONTEXT)


def _in_memory_worker(monkeypatch, delivering: EmailSender, *, inplace: bool) -> InMemoryBroker:
    broker = InMemoryBroker(await_inplace=inplace)
    broker.register_task(send_email.original_func, task_name=EMAIL_TASK_NAME, retry_on_error=True)
    monkeypatch.setattr(send_email, "broker", broker)
    monkeypatch.setattr(taskiq_email, "sender", delivering)

    return broker


async def test_the_message_the_worker_delivers_is_the_one_that_was_enqueued(monkeypatch):
    """Everything the sender needs to render the email survives the queue, link included."""
    delivering = _Capturing()
    _in_memory_worker(monkeypatch, delivering, inplace=True)

    await _enqueue_the_verification_email()

    assert delivering.sent == [{"to": RECIPIENT, "subject": SUBJECT, "body": BODY, "kind": "verify_email", "context": CONTEXT}]


async def test_the_caller_does_not_wait_for_delivery(monkeypatch):
    """Enqueueing returns before the task runs, so a slow mail server never holds a request."""
    delivering = _Capturing()
    broker = _in_memory_worker(monkeypatch, delivering, inplace=False)

    await _enqueue_the_verification_email()
    enqueued = delivering.sent.copy()
    await broker.wait_all()

    assert enqueued == []
    assert len(delivering.sent) == 1


def test_a_misconfigured_backend_is_refused_when_the_worker_module_loads():
    """The import has to fail the way the direct path's does, not every message later."""
    environment = {**os.environ, "PYTHONPATH": str(BACKEND), "EMAIL_BACKEND": "smtp", "EMAIL_SMTP_HOST": ""}

    result = subprocess.run(
        [sys.executable, "-c", _IMPORT_THE_SENDER], cwd=BACKEND, env=environment, capture_output=True, text=True
    )

    assert result.returncode != 0
    assert "EMAIL_SMTP_HOST" in result.stderr
