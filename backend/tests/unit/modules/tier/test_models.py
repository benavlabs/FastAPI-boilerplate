"""Unit tests for the Tier ORM model configuration."""

from sqlalchemy import inspect

from src.modules.tier.models import Tier


def test_tier_users_is_lazy_select():
    """Loading a tier must not load every user assigned to it."""
    rel = inspect(Tier).relationships["users"]
    assert rel.lazy == "select", f"Tier.users should be lazy='select', got {rel.lazy!r}"
