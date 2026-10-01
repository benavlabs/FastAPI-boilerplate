"""Tests for the User admin view's password handling."""

import threading
from types import SimpleNamespace
from typing import cast
from unittest.mock import patch

import bcrypt
import pytest
from crudauth.exceptions import PasswordPolicyException
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.modules.user.admin import UserAdmin
from src.modules.user.models import User
from tests.unit.interfaces.admin.helpers import exported_rows


def _no_request() -> Request:
    """The view reads nothing off the request."""
    return cast(Request, None)


async def test_the_admin_form_hashes_the_password_off_the_event_loop():
    """bcrypt is deliberately slow; on the loop thread it would stall every other request."""
    real_hashpw = bcrypt.hashpw
    threads: list[str] = []

    def recording_hashpw(password, salt):
        threads.append(threading.current_thread().name)
        return real_hashpw(password, salt)

    data = {"hashed_password": "Str1ngst!"}
    with patch.object(bcrypt, "hashpw", recording_hashpw):
        await UserAdmin().on_model_change(data, model=None, is_created=True, request=_no_request())

    assert data["hashed_password"] != "Str1ngst!"
    assert data["hashed_password"]
    assert threads
    assert threading.main_thread().name not in threads


async def test_the_admin_form_refuses_a_password_that_breaks_the_policy():
    with pytest.raises(PasswordPolicyException):
        await UserAdmin().on_model_change({"hashed_password": "weak"}, model=None, is_created=True, request=_no_request())


async def test_the_admin_form_turns_a_blank_oauth_provider_into_none():
    data = {"oauth_provider": ""}

    await UserAdmin().on_model_change(data, model=None, is_created=False, request=_no_request())

    assert data["oauth_provider"] is None


async def test_the_admin_panel_stores_the_address_in_canonical_form():
    """A row written in the panel is signed in to through crudauth, which lowercases."""
    data = {"name": "Mixed Case", "username": "mixedcase", "email": "Admin@Example.COM"}

    await UserAdmin().on_model_change(data, SimpleNamespace(email="admin@example.com"), False, _no_request())

    assert data["email"] == "admin@example.com"


async def test_changing_the_address_in_the_panel_clears_the_verification():
    """The new address hasn't been proven, whoever typed it."""
    data = {"email": "new@example.com"}

    await UserAdmin().on_model_change(data, SimpleNamespace(email="old@example.com"), False, _no_request())

    assert data["email_verified"] is False


async def test_saving_the_same_address_in_another_case_keeps_the_verification():
    """A row stored before addresses were canonicalised must not lose its flag on every save."""
    data = {"email": "Legacy@Example.com"}

    await UserAdmin().on_model_change(data, SimpleNamespace(email="Legacy@Example.com"), False, _no_request())

    assert "email_verified" not in data


async def test_creating_a_row_says_nothing_about_verification():
    data = {"email": "fresh@example.com", "hashed_password": "Str1ngst!"}

    await UserAdmin().on_model_change(data, None, True, _no_request())

    assert "email_verified" not in data


class TestWhatThePanelShows:
    """The password hash never reaches a page, and the tier selector has to render."""

    def test_the_password_hash_is_in_neither_the_list_nor_the_detail_view(self):
        view = UserAdmin()

        assert "hashed_password" not in view._list_prop_names
        assert "hashed_password" not in view._details_prop_names
        assert "hashed_password" not in view._export_prop_names

    async def test_the_tier_field_renders_on_both_forms(self, db_session: AsyncSession, monkeypatch):
        """The form rule names the ``tier`` relationship, which sqladmin scaffolds into a field."""
        view = UserAdmin()
        maker = async_sessionmaker(bind=db_session.bind, class_=AsyncSession, expire_on_commit=False)
        monkeypatch.setattr(UserAdmin, "session_maker", maker, raising=False)

        create_fields = (await view.scaffold_form(view.form_create_rules))()._fields
        edit_fields = (await view.scaffold_form(view.form_edit_rules))()._fields

        assert "tier" in create_fields
        assert "tier" in edit_fields
        assert "hashed_password" not in edit_fields


async def test_the_panel_refuses_to_put_a_user_on_a_deleted_tier():
    """The form's tier list comes from sqladmin and includes deleted rows."""
    data = {"tier": SimpleNamespace(id=7, is_deleted=True)}

    with pytest.raises(ValueError, match="deleted"):
        await UserAdmin().on_model_change(data, SimpleNamespace(email="x@example.com"), False, _no_request())


async def test_the_panel_accepts_a_live_tier():
    data = {"tier": SimpleNamespace(id=7, is_deleted=False)}

    await UserAdmin().on_model_change(data, SimpleNamespace(email="x@example.com"), False, _no_request())

    assert data["tier"].id == 7


def test_the_form_rules_name_only_fields_the_model_has():
    """Every form rule names a column or a relationship of the model."""
    mapper = User.__mapper__
    known = set(mapper.columns.keys()) | set(mapper.relationships.keys())

    assert set(UserAdmin.form_edit_rules) <= known
    assert set(UserAdmin.form_create_rules) <= known


class TestTheCsvExport:
    """Cells a spreadsheet would run as a formula leave the panel as text."""

    @pytest.fixture
    def view(self, db_session: AsyncSession, monkeypatch) -> UserAdmin:
        maker = async_sessionmaker(bind=db_session.bind, class_=AsyncSession, expire_on_commit=False)
        monkeypatch.setattr(UserAdmin, "session_maker", maker, raising=False)

        return UserAdmin()

    async def _user(self, db_session: AsyncSession, name: str, username: str) -> User:
        user = User(
            name=name,
            username=username,
            email=f"{username}@example.com",
            hashed_password="not-a-hash",
            is_superuser=False,
        )
        db_session.add(user)
        await db_session.commit()

        return user

    async def test_a_name_that_looks_like_a_formula_is_exported_as_text(self, view: UserAdmin, db_session: AsyncSession):
        user = await self._user(db_session, "=cmd|' /C calc'!A0", "formula")

        header, row = await exported_rows(view, [user])

        assert row[header.index("name")] == "'=cmd|' /C calc'!A0"

    async def test_an_ordinary_name_is_exported_unchanged(self, view: UserAdmin, db_session: AsyncSession):
        user = await self._user(db_session, "Ada Lovelace", "ada")

        header, row = await exported_rows(view, [user])

        assert row[header.index("name")] == "Ada Lovelace"

    async def test_the_pretty_export_writes_it_as_text_too(self, view: UserAdmin, db_session: AsyncSession, monkeypatch):
        monkeypatch.setattr(UserAdmin, "use_pretty_export", True)
        user = await self._user(db_session, "=cmd|' /C calc'!A0", "prettyformula")

        header, row = await exported_rows(view, [user])

        assert "'=cmd|' /C calc'!A0" in row
        assert row[header.index("id")] == str(user.id)
