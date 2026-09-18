"""Tests for the Tier admin view configuration."""

from src.interfaces.admin.views.tiers import TierAdmin


def test_tier_admin_form_does_not_include_users():
    """The tier form must not preload a tier's users or list every user as an option."""
    assert "users" not in TierAdmin().get_form_columns()


def test_tier_admin_details_do_not_include_users():
    """The tier details page must not preload every user assigned to the tier."""
    assert "users" not in TierAdmin().get_details_columns()
