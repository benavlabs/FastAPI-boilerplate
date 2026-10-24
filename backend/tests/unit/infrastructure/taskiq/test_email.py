"""Handing an account email to the worker, and what arrives there."""

import asyncio
import json
import logging
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import anyio
from crudauth import EmailContext, EmailSender
from crudauth.email.constants import EmailKind
from cryptography.fernet import Fernet
from taskiq import InMemoryBroker

from src.infrastructure.handover import drain
from src.infrastructure.taskiq import email as taskiq_email
from src.infrastructure.taskiq import sealing
from src.infrastructure.taskiq.email import EMAIL_TASK_NAME, queued_sender, send_email
from src.infrastructure.taskiq.sealing import seal

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


async def _hand_over_and_wait() -> None:
    """Send, then wait for what the sender handed over, which a shutdown waits for too."""
    await _enqueue_the_verification_email()
    await drain()


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

    await _hand_over_and_wait()

    assert delivering.sent == [{"to": RECIPIENT, "subject": SUBJECT, "body": BODY, "kind": "verify_email", "context": CONTEXT}]


async def test_the_caller_does_not_wait_for_delivery(monkeypatch):
    """Sending returns before the message is even queued, let alone delivered."""
    delivering = _Capturing()
    broker = _in_memory_worker(monkeypatch, delivering, inplace=False)

    await _enqueue_the_verification_email()
    enqueued = delivering.sent.copy()
    await drain()
    await broker.wait_all()

    assert enqueued == []
    assert len(delivering.sent) == 1


async def test_the_queue_carries_nothing_a_recovery_link_can_be_read_from(monkeypatch):
    """Whoever reads the queue, or a backup of one, would otherwise read every link in it."""
    delivering = _Capturing()
    broker = _in_memory_worker(monkeypatch, delivering, inplace=False)
    enqueued: list[bytes] = []
    reached_the_queue = broker.kick

    async def watching(message: Any) -> None:
        enqueued.append(message.message)
        await reached_the_queue(message)

    monkeypatch.setattr(broker, "kick", watching)

    await _hand_over_and_wait()
    await broker.wait_all()

    carried = enqueued[0]
    assert b"the-signed-token" not in carried
    assert LINK.encode() not in carried and BODY.encode() not in carried
    assert RECIPIENT.encode() not in carried
    assert delivering.sent == [{"to": RECIPIENT, "subject": SUBJECT, "body": BODY, "kind": "verify_email", "context": CONTEXT}]


async def test_a_message_the_worker_cannot_open_is_dropped_rather_than_retried(monkeypatch, caplog):
    """``SECRET_KEY`` changed while it waited, and no retry will open it either.

    The error names the task and nothing of the message, which was sealed for a reason.
    """
    delivering = _Capturing()
    _in_memory_worker(monkeypatch, delivering, inplace=True)
    sealed_under_the_old_key = seal({"to": RECIPIENT, "subject": SUBJECT, "body": BODY, "kind": "verify_email", "link": LINK})
    monkeypatch.setattr(sealing.settings, "SECRET_KEY", "the-key-this-project-turned-over-to")

    with caplog.at_level(logging.ERROR):
        await send_email.original_func(sealed=sealed_under_the_old_key, expires_in=7200)

    assert delivering.sent == []
    assert EMAIL_TASK_NAME in caplog.text
    assert RECIPIENT not in caplog.text and LINK not in caplog.text


async def test_a_message_that_waited_longer_than_its_link_lives_is_dropped(monkeypatch, caplog):
    """Delivering it would send somebody a page that says only that the link has expired."""
    delivering = _Capturing()
    _in_memory_worker(monkeypatch, delivering, inplace=True)
    message = {"to": RECIPIENT, "subject": SUBJECT, "body": BODY, "kind": "verify_email", "link": LINK}
    waited = Fernet(sealing._key()).encrypt_at_time(json.dumps(message).encode(), int(time.time()) - 7300)

    with caplog.at_level(logging.ERROR):
        await send_email.original_func(sealed=waited.decode(), expires_in=7200)

    assert delivering.sent == []
    assert EMAIL_TASK_NAME in caplog.text
    assert RECIPIENT not in caplog.text and LINK not in caplog.text


async def test_a_message_that_names_no_lifetime_is_delivered_however_long_it_waited(monkeypatch):
    """A notice carries no link, so it has nothing that runs out.

    ``existing_account`` is one: it tells an account somebody tried to sign up with its
    address, and there is nothing in it to click.
    """
    delivering = _Capturing()
    _in_memory_worker(monkeypatch, delivering, inplace=True)
    notice = {
        "to": RECIPIENT,
        "subject": "Somebody tried to sign up with your address",
        "body": "You already have an account.",
        "kind": "existing_account",
        "link": None,
    }
    waited = Fernet(sealing._key()).encrypt_at_time(json.dumps(notice).encode(), int(time.time()) - 86400)

    await send_email.original_func(sealed=waited.decode(), expires_in=0)

    assert [sent["to"] for sent in delivering.sent] == [RECIPIENT]
    assert delivering.sent[0]["kind"] == "existing_account"


async def test_a_publish_that_cannot_finish_does_not_delay_the_caller(monkeypatch):
    """A recovery route sends only where the address has an account.

    So a route that waited for the publish would answer slowly for an address that exists
    and quickly for one that does not, which is the thing no answer gives away. The call is
    given a second of its own, so a sender that waits again fails this rather than hanging.
    """
    delivering = _Capturing()
    broker = _in_memory_worker(monkeypatch, delivering, inplace=True)
    let_it_finish = asyncio.Event()

    async def waiting(message: Any) -> None:
        await let_it_finish.wait()

    monkeypatch.setattr(broker, "kick", waiting)

    with anyio.fail_after(1):
        await _enqueue_the_verification_email()

    assert delivering.sent == []
    let_it_finish.set()
    await drain()


async def test_a_message_the_broker_will_not_take_is_delivered_anyway(monkeypatch, caplog):
    """A message is best-effort to crudauth, which logs what a channel raises and answers 200.

    So an enqueue nothing catches loses the mail: the account that asked for a reset link
    never gets one, and the answer says nothing about it. Delivering it from the handover
    is slower than the queue and is what the message is worth.
    """
    delivering = _Capturing()
    broker = _in_memory_worker(monkeypatch, delivering, inplace=True)

    async def unreachable(message: Any) -> None:
        raise ConnectionError("the broker is unreachable")

    monkeypatch.setattr(broker, "kick", unreachable)

    with caplog.at_level(logging.WARNING):
        await _hand_over_and_wait()

    assert delivering.sent == [{"to": RECIPIENT, "subject": SUBJECT, "body": BODY, "kind": "verify_email", "context": CONTEXT}]
    assert "verify_email" in caplog.text


async def test_a_message_neither_the_queue_nor_the_sender_takes_is_logged(monkeypatch, caplog):
    """Nothing is waiting on this to answer anybody, so the log is all that is left of it."""
    delivering = _Capturing()
    broker = _in_memory_worker(monkeypatch, delivering, inplace=True)

    async def unreachable(message: Any) -> None:
        raise ConnectionError("the broker is unreachable")

    async def refused(**message: Any) -> None:
        raise ConnectionRefusedError("no mail server either")

    monkeypatch.setattr(broker, "kick", unreachable)
    monkeypatch.setattr(delivering, "send", refused)

    with caplog.at_level(logging.WARNING):
        await _hand_over_and_wait()

    assert delivering.sent == []
    assert "Could not deliver a verify_email email at all" in caplog.text


async def test_a_broker_that_never_answers_still_ends_in_a_delivery(monkeypatch, caplog):
    """A refusal is the quick failure; a broker that accepts and stalls is the slow one.

    The timeout is shortened here, so the test waits for it rather than the five seconds a
    shutdown would, and the whole call is given a second of its own, so a sender that
    stopped bounding the enqueue fails this rather than hanging the suite.
    """
    delivering = _Capturing()
    broker = _in_memory_worker(monkeypatch, delivering, inplace=True)

    async def never_answers(message: Any) -> None:
        await anyio.sleep_forever()

    monkeypatch.setattr(broker, "kick", never_answers)
    monkeypatch.setattr(taskiq_email, "BROKER_CONNECT_SECONDS", 0.05)

    with caplog.at_level(logging.WARNING), anyio.fail_after(1):
        await _hand_over_and_wait()

    assert delivering.sent == [{"to": RECIPIENT, "subject": SUBJECT, "body": BODY, "kind": "verify_email", "context": CONTEXT}]
    assert "verify_email" in caplog.text


async def test_a_message_the_broker_takes_is_not_delivered_twice(monkeypatch):
    """The control: the queue is still what delivers when the broker is there."""
    delivering = _Capturing()
    broker = _in_memory_worker(monkeypatch, delivering, inplace=False)

    await _enqueue_the_verification_email()
    before_the_worker_ran = len(delivering.sent)
    await drain()
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
