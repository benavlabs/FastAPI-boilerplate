"""The log lines a refused sign-in leaves, and what they keep out of the log."""

import logging

from crudauth import HookContext

from src.infrastructure.auth.audit import record_a_lockout, record_a_refused_login
from src.infrastructure.auth.setup import auth

CALLER = HookContext(ip_address="203.0.113.7", user_agent="curl/8.4.0")


async def test_a_refusal_on_an_account_that_exists_names_it_with_the_reason_and_the_caller(caplog):
    with caplog.at_level(logging.WARNING):
        await record_a_refused_login("ada", user={"id": 1}, reason="invalid_credentials", context=CALLER)

    assert "'ada'" in caplog.text
    assert "invalid_credentials" in caplog.text
    assert "203.0.113.7" in caplog.text
    assert "curl/8.4.0" in caplog.text


async def test_an_identifier_no_account_has_is_never_written_out(caplog):
    """The username field is where a password lands when someone types one box too high."""
    with caplog.at_level(logging.WARNING):
        await record_a_refused_login("hunter2!", user=None, reason="invalid_credentials", context=CALLER)

    assert "hunter2" not in caplog.text
    assert "an identifier no account has" in caplog.text
    assert "203.0.113.7" in caplog.text
    assert "curl/8.4.0" in caplog.text


async def test_a_disabled_account_is_named_and_told_apart_from_a_wrong_password(caplog):
    """The route answers 401 for both; only the log says which refusal it was."""
    with caplog.at_level(logging.WARNING):
        await record_a_refused_login("ada", user={"id": 1}, reason="inactive", context=CALLER)

    assert "'ada'" in caplog.text
    assert "inactive" in caplog.text


async def test_a_lockout_names_how_long_it_refuses_for_and_no_identifier(caplog):
    """Nothing resolves the identifier before the lockout refuses, so none is recorded."""
    with caplog.at_level(logging.WARNING):
        await record_a_lockout("hunter2!", retry_after=300, context=CALLER)

    assert "300s" in caplog.text
    assert "203.0.113.7" in caplog.text
    assert "hunter2" not in caplog.text


async def test_a_caller_behind_no_proxy_is_still_recorded(caplog):
    """A hook called with neither header set must log the refusal, not raise over it."""
    with caplog.at_level(logging.WARNING):
        await record_a_refused_login("ada", user={"id": 1}, reason="invalid_credentials", context=HookContext())

    assert "an unknown address" in caplog.text
    assert "no user agent" in caplog.text


def test_both_hooks_are_registered():
    assert auth.hooks.on_login_failed is record_a_refused_login
    assert auth.hooks.on_lockout is record_a_lockout
