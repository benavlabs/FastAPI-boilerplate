"""Unit tests for the User model."""

from src.modules.user.models import User


def _make_user() -> User:
    return User(
        name="Test User",
        username="testuser",
        email="test@example.com",
        hashed_password="hashed",
    )


def test_is_active_true_when_not_deleted():
    """A fresh user is active (is_deleted defaults to False)."""
    user = _make_user()
    assert user.is_deleted is False
    assert user.is_active is True


def test_is_active_false_when_soft_deleted():
    """A soft-deleted user is inactive — this is what crudauth reads to gate auth."""
    user = _make_user()
    user.is_deleted = True
    assert user.is_active is False
