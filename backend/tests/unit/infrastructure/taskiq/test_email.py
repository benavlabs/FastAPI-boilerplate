"""Handing an account email to the worker, and what arrives there."""

import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import anyio
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


async def test_a_message_the_broker_will_not_take_is_delivered_in_the_request(monkeypatch, caplog):
    """A message is best-effort to crudauth, which logs what a channel raises and answers 200.

    So an enqueue nothing catches loses the mail: the account that asked for a reset link
    never gets one, and the answer says nothing about it. Delivering in the request is
    slower than the queue and is what the message is worth.
    """
    delivering = _Capturing()
    broker = _in_memory_worker(monkeypatch, delivering, inplace=True)

    async def unreachable(message: Any) -> None:
        raise ConnectionError("the broker is unreachable")

    monkeypatch.setattr(broker, "kick", unreachable)

    with caplog.at_level(logging.WARNING):
        await _enqueue_the_verification_email()

    assert delivering.sent == [{"to": RECIPIENT, "subject": SUBJECT, "body": BODY, "kind": "verify_email", "context": CONTEXT}]
    assert "verify_email" in caplog.text


async def test_a_broker_that_never_answers_does_not_hold_the_request(monkeypatch, caplog):
    """A refusal is the quick failure; a broker that accepts and stalls is the slow one.

    The timeout is shortened here, so the test waits for it rather than the five seconds a
    request would, and the whole call is given a second of its own, so a sender that stopped
    bounding the enqueue fails this rather than hanging the suite.
    """
    delivering = _Capturing()
    broker = _in_memory_worker(monkeypatch, delivering, inplace=True)

    async def never_answers(message: Any) -> None:
        await anyio.sleep_forever()

    monkeypatch.setattr(broker, "kick", never_answers)
    monkeypatch.setattr(taskiq_email, "BROKER_CONNECT_SECONDS", 0.05)

    with caplog.at_level(logging.WARNING), anyio.fail_after(1):
        await _enqueue_the_verification_email()

    assert delivering.sent == [{"to": RECIPIENT, "subject": SUBJECT, "body": BODY, "kind": "verify_email", "context": CONTEXT}]
    assert "verify_email" in caplog.text


async def test_a_message_the_broker_takes_is_not_delivered_twice(monkeypatch):
    """The control: the queue is still what delivers when the broker is there."""
    delivering = _Capturing()
    broker = _in_memory_worker(monkeypatch, delivering, inplace=False)

    await _enqueue_the_verification_email()
    before_the_worker_ran = len(delivering.sent)
    await broker.wait_all()

    assert (before_the_worker_ran, len(delivering.sent)) == (0, 1)


def test_a_misconfigured_backend_is_refused_when_the_worker_module_loads():
    """The import has to fail the way the direct path's does, not every message later."""
    environment = {**os.environ, "PYTHONPATH": str(BACKEND), "EMAIL_BACKEND": "smtp", "EMAIL_SMTP_HOST": ""}

    result = subprocess.run(
        [sys.executable, "-c", _IMPORT_THE_SENDER], cwd=BACKEND, env=environment, capture_output=True, text=True
    )

    assert result.returncode != 0
    assert "EMAIL_SMTP_HOST" in result.stderr


_FIND_THE_TASK = """
import src.infrastructure.taskiq.{entry} as entry

broker = getattr(entry, "default_broker", None) or entry.scheduler.broker
print("FOUND" if broker.find_task("{task}") is not None else "MISSING")
"""


def _entry_point_tasks(entry: str) -> str:
    """What a cold ``taskiq worker``/``taskiq scheduler`` process finds on the broker it is handed.

    The task name is passed in rather than imported, since importing the module that
    declares it is what the entry point has to do for itself.
    """
    environment = {**os.environ, "PYTHONPATH": str(BACKEND)}

    result = subprocess.run(
        [sys.executable, "-c", _FIND_THE_TASK.format(entry=entry, task=EMAIL_TASK_NAME)],
        cwd=BACKEND,
        env=environment,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    return result.stdout.strip().splitlines()[-1]


def test_the_worker_entry_point_registers_the_email_task():
    """``taskiq worker …:default_broker`` runs with no task discovery, so the entry point imports them."""
    assert _entry_point_tasks("worker") == "FOUND"


def test_the_scheduler_entry_point_registers_the_email_task():
    assert _entry_point_tasks("scheduler") == "FOUND"
