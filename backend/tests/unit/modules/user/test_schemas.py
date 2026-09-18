"""Unit tests for the User schemas."""

import pytest
from pydantic import ValidationError

from src.modules.user.schemas import UserCreate


def _user_data(password: str) -> dict[str, str]:
    return {
        "name": "Test User",
        "username": "testuser",
        "email": "user.userson@example.com",
        "password": password,
    }


def test_password_with_every_character_class_is_accepted():
    """The documented example must keep working."""
    user = UserCreate(**_user_data("Str1ngst!"))

    assert user.password == "Str1ngst!"


@pytest.mark.parametrize(
    ("password", "missing"),
    [
        ("str1ngst!", "uppercase letter"),
        ("STR1NGST!", "lowercase letter"),
        ("Stringst!", "number"),
        ("Str1ngst", "special character"),
        ("abcdefgh", "uppercase letter"),
        ("aaaaaaaaaaaa", "uppercase letter"),
        ("        ", "lowercase letter"),
    ],
)
def test_password_missing_a_character_class_is_rejected(password: str, missing: str):
    """A password is rejected when any class from the description is missing."""
    with pytest.raises(ValidationError, match=missing):
        UserCreate(**_user_data(password))


def test_a_non_latin_password_is_accepted():
    """Character classes are Unicode-aware, so a Cyrillic password has lowercase letters."""
    user = UserCreate(**_user_data("Пароль1!"))

    assert user.password == "Пароль1!"


def test_an_accented_letter_is_not_a_special_character():
    """``é`` is a letter, so it doesn't satisfy the special-character requirement."""
    with pytest.raises(ValidationError, match="special character"):
        UserCreate(**_user_data("Senhaé123"))


@pytest.mark.parametrize("password", ["Str1ng!", "Ab1!cde"])
def test_password_shorter_than_eight_characters_is_rejected(password: str):
    """Length stays enforced separately from the character classes."""
    with pytest.raises(ValidationError, match="at least 8 characters"):
        UserCreate(**_user_data(password))
