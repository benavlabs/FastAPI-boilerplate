"""Tests for the User admin view's password handling."""

import threading
from types import SimpleNamespace
from unittest.mock import patch

import bcrypt
import pytest
from crudauth.exceptions import PasswordPolicyException
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.modules.user.admin import UserAdmin
from src.modules.user.models import User


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


async def test_the_admin_panel_stores_the_address_in_canonical_form():
    """A row written in the panel is signed in to through crudauth, which lowercases."""
    data = {"name": "Mixed Case", "username": "mixedcase", "email": "Admin@Example.COM"}

    await UserAdmin().on_model_change(data, SimpleNamespace(email="admin@example.com"), False, None)

    assert data["email"] == "admin@example.com"


async def test_changing_the_address_in_the_panel_clears_the_verification():
    """The new address hasn't been proven, whoever typed it."""
    data = {"email": "new@example.com"}

    await UserAdmin().on_model_change(data, SimpleNamespace(email="old@example.com"), False, None)

    assert data["email_verified"] is False


async def test_saving_the_same_address_in_another_case_keeps_the_verification():
    """A row stored before addresses were canonicalised must not lose its flag on every save."""
    data = {"email": "Legacy@Example.com"}

    await UserAdmin().on_model_change(data, SimpleNamespace(email="Legacy@Example.com"), False, None)

    assert "email_verified" not in data


async def test_creating_a_row_says_nothing_about_verification():
    data = {"email": "fresh@example.com", "hashed_password": "Str1ngst!"}

    await UserAdmin().on_model_change(data, None, True, None)

    assert "email_verified" not in data


class TestWhatThePanelShows:
    """The password hash never reaches a page, and the tier selector has to render."""

    def test_the_password_hash_is_in_neither_the_list_nor_the_detail_view(self):
        view = UserAdmin()

        assert "hashed_password" not in view._list_prop_names
        assert "hashed_password" not in view._details_prop_names
        assert "hashed_password" not in view._export_prop_names

    async def test_the_tier_field_renders_on_both_forms(self, db_session: AsyncSession):
        """sqladmin drops foreign-key columns from forms, so the rule names the relationship."""
        view = UserAdmin()
        view.session_maker = async_sessionmaker(bind=db_session.bind, class_=AsyncSession, expire_on_commit=False)

        create_fields = (await view.scaffold_form(view.form_create_rules))()._fields
        edit_fields = (await view.scaffold_form(view.form_edit_rules))()._fields

        assert "tier" in create_fields
        assert "tier" in edit_fields
        assert "hashed_password" not in edit_fields


async def test_the_panel_refuses_to_put_a_user_on_a_deleted_tier():
    """The form's tier list comes from sqladmin and includes deleted rows."""
    data = {"tier": SimpleNamespace(id=7, is_deleted=True)}

    with pytest.raises(ValueError, match="deleted"):
        await UserAdmin().on_model_change(data, SimpleNamespace(email="x@example.com"), False, None)


async def test_the_panel_accepts_a_live_tier():
    data = {"tier": SimpleNamespace(id=7, is_deleted=False)}

    await UserAdmin().on_model_change(data, SimpleNamespace(email="x@example.com"), False, None)

    assert data["tier"].id == 7


def test_the_form_rules_name_only_fields_the_model_has():
    """Every form rule names a column or a relationship of the model."""
    mapper = User.__mapper__
    known = set(mapper.columns.keys()) | set(mapper.relationships.keys())

    assert set(UserAdmin.form_edit_rules) <= known
    assert set(UserAdmin.form_create_rules) <= known
