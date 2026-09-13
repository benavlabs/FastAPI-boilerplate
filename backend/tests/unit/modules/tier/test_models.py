"""Unit tests for the Tier ORM model configuration."""

from sqlalchemy import inspect

from src.modules.tier.models import Tier


def test_tier_users_is_lazy_select():
    """Tier.users must lazy-load, not eager-load.

    Regression lock: this was ``lazy="selectin"``, which loaded every user in a
    tier whenever a Tier was loaded (e.g. SQLAdmin's tier list, where most users
    sit in the default tier). ``lazy="select"`` defers loading until the
    attribute is accessed.
    """
    rel = inspect(Tier).relationships["users"]
    assert rel.lazy == "select", f"Tier.users should be lazy='select', got {rel.lazy!r}"
