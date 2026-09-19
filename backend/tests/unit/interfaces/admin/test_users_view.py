"""Tests for the User admin view's password handling."""

import threading
from unittest.mock import patch

import bcrypt
import pytest
from crudauth.exceptions import PasswordPolicyException

from src.interfaces.admin.views.users import UserAdmin


async def test_the_admin_form_hashes_the_password_off_the_event_loop():
    """bcrypt is deliberately slow; on the loop thread it would stall every other request."""
    real_hashpw = bcrypt.hashpw
    threads: list[str] = []

    def recording_hashpw(password, salt):
        threads.append(threading.current_thread().name)
        return real_hashpw(password, salt)

    data = {"hashed_password": "Str1ngst!"}
    with patch.object(bcrypt, "hashpw", recording_hashpw):
        await UserAdmin().on_model_change(data, model=None, is_created=True, request=None)

    assert data["hashed_password"] != "Str1ngst!"
    assert data["hashed_password"]
    assert threads
    assert threading.main_thread().name not in threads


async def test_the_admin_form_refuses_a_password_that_breaks_the_policy():
    with pytest.raises(PasswordPolicyException):
        await UserAdmin().on_model_change({"hashed_password": "weak"}, model=None, is_created=True, request=None)


async def test_the_admin_form_turns_a_blank_oauth_provider_into_none():
    data = {"oauth_provider": ""}

    await UserAdmin().on_model_change(data, model=None, is_created=False, request=None)

    assert data["oauth_provider"] is None
