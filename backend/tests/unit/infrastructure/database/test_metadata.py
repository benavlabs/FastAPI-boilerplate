"""The shared metadata names constraints by the standard convention.

The convention is core's; that a feature's own tables follow it is checked with
that feature, in ``tests/unit/modules/api_keys/test_metadata.py``.
"""

from src.infrastructure.database.session import NAMING_CONVENTION


def test_the_convention_covers_every_constraint_kind():
    assert set(NAMING_CONVENTION) == {"ix", "uq", "ck", "fk", "pk"}
