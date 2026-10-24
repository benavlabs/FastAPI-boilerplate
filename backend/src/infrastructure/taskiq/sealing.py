"""Keeping what a queued message carries from whoever can read the queue."""

import base64
import hashlib
import hmac
import json
from collections.abc import Mapping
from typing import Any

from cryptography.fernet import Fernet

from ..config.settings import get_settings

settings = get_settings()

SEAL_LABEL = b"taskiq-email-seal"
"""What this key is for, mixed in so no other use of ``SECRET_KEY`` can arrive at the same one."""


def _key() -> bytes:
    """The key a message is sealed with, derived from ``SECRET_KEY`` for this one use.

    ``SECRET_KEY`` signs the sessions and the CSRF tokens and salts the admin fingerprint
    already, so the derivation carries ``SEAL_LABEL``: a feature that reaches for the
    obvious ``sha256(SECRET_KEY)`` later gets a key of its own rather than this one.

    A keyed digest rather than a slow derivation: ``SECRET_KEY`` is the project's own
    secret and is meant to be long and random, so there is no guessing for a work factor
    to slow.
    """
    return base64.urlsafe_b64encode(hmac.new(settings.SECRET_KEY.encode(), SEAL_LABEL, hashlib.sha256).digest())


def seal(payload: Mapping[str, Any]) -> str:
    """``payload`` as one string, which nothing without ``SECRET_KEY`` can read or forge."""
    return Fernet(_key()).encrypt(json.dumps(dict(payload)).encode()).decode()


def unseal(sealed: str, within: int | None = None) -> dict[str, Any]:
    """What ``seal`` was given, where it was sealed less than ``within`` seconds ago.

    A seal carries the time it was made, so ``within`` is how a caller refuses one that
    waited too long: a message holding a link that has since expired is one nobody can
    use. ``None`` accepts it however long it waited.

    Raises:
        InvalidToken: ``sealed`` was not written by ``seal`` under this ``SECRET_KEY``, has
            been changed since, or was sealed longer than ``within`` seconds ago.
    """
    opened: dict[str, Any] = json.loads(Fernet(_key()).decrypt(sealed.encode(), ttl=within))

    return opened
