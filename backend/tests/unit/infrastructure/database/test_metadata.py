"""The shared metadata uses the standard constraint naming convention."""

from src.infrastructure.database.session import NAMING_CONVENTION, Base


def test_metadata_uses_the_standard_naming_convention():
    """Stable names keep Alembic autogenerate from renaming constraints on every run."""
    assert dict(Base.metadata.naming_convention) == NAMING_CONVENTION
    assert set(NAMING_CONVENTION) == {"ix", "uq", "ck", "fk", "pk"}
