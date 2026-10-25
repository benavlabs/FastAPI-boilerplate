"""What a sealed message keeps from whoever can read the queue it waits in."""

import base64
import hashlib
import json
import time

import pytest
from cryptography.fernet import Fernet, InvalidToken

from src.infrastructure.taskiq import sealing
from src.infrastructure.taskiq.sealing import seal, unseal

MESSAGE = {
    "to": "owner@example.com",
    "subject": "Reset your password",
    "link": "https://app/reset?token=abc",
    "expires_in": 3600,
}


def test_a_message_comes_back_as_it_was_sealed():
    assert unseal(seal(MESSAGE)) == MESSAGE


def test_a_sealed_message_reads_as_nothing_without_the_key():
    sealed = seal(MESSAGE)

    assert "owner@example.com" not in sealed
    assert "token=abc" not in sealed


def test_a_message_sealed_under_another_secret_cannot_be_opened(monkeypatch):
    """The worker reads ``SECRET_KEY`` as the request did, so a key change ends in a refusal."""
    sealed = seal(MESSAGE)
    monkeypatch.setattr(sealing.settings, "SECRET_KEY", "a-different-secret-entirely")

    with pytest.raises(InvalidToken):
        unseal(sealed)


def test_the_key_is_this_one_use_of_the_secret_and_not_a_digest_of_it():
    """A later feature reaching for ``sha256(SECRET_KEY)`` must not arrive at this key."""
    plain_digest = base64.urlsafe_b64encode(hashlib.sha256(sealing.settings.SECRET_KEY.encode()).digest())

    with pytest.raises(InvalidToken):
        Fernet(plain_digest).decrypt(seal(MESSAGE).encode())


def _sealed_at(seconds_ago: int) -> str:
    """A message sealed that long ago, since a seal carries the time it was made."""
    at = int(time.time()) - seconds_ago

    return Fernet(sealing._key()).encrypt_at_time(json.dumps(MESSAGE).encode(), at).decode()


def test_a_message_sealed_longer_ago_than_the_link_lives_is_refused():
    """A queue that stood still holds links nobody can use any more."""
    with pytest.raises(InvalidToken):
        unseal(_sealed_at(120), within=60)


def test_a_message_sealed_inside_the_time_it_names_is_opened():
    assert unseal(_sealed_at(10), within=60) == MESSAGE


def test_a_message_that_names_no_lifetime_is_opened_however_long_it_waited():
    """A message carrying no link has nothing that runs out."""
    assert unseal(_sealed_at(86400)) == MESSAGE


def test_a_string_nothing_sealed_is_refused():
    with pytest.raises(InvalidToken):
        unseal("not-a-sealed-message")


def test_a_sealed_message_that_was_changed_is_refused():
    """A queue anybody can write would otherwise be a queue anybody can put a link in."""
    sealed = seal(MESSAGE)
    tampered = sealed[:-4] + ("AAAA" if not sealed.endswith("AAAA") else "BBBB")

    with pytest.raises(InvalidToken):
        unseal(tampered)
