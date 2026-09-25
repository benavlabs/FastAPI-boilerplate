"""The shared metadata names constraints by the standard convention.

Stable names keep Alembic autogenerate from renaming constraints on every run, so
these pin the names the convention produces rather than the convention itself.
"""

import src.modules.api_keys.models  # noqa: F401  (registers the tables)
from src.infrastructure.database.session import NAMING_CONVENTION, Base

API_KEYS = "api_keys"


def test_the_convention_covers_every_constraint_kind():
    assert set(NAMING_CONVENTION) == {"ix", "uq", "ck", "fk", "pk"}


def test_a_column_index_carries_the_table_in_its_name():
    indexes = {index.name for index in Base.metadata.tables[API_KEYS].indexes}

    assert {"ix_api_keys_user_id", "ix_api_keys_key_hash"} <= indexes


def test_keys_are_named_after_their_table_and_columns():
    table = Base.metadata.tables[API_KEYS]

    assert table.primary_key.name == "pk_api_keys"
    assert {constraint.name for constraint in table.foreign_key_constraints} == {"fk_api_keys_user_id_user"}
