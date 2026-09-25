"""The api_keys tables must not declare the same index twice."""

import src.modules.api_keys.models  # noqa: F401  (registers the tables)
from src.infrastructure.database.session import Base

API_KEYS_TABLES = ("api_keys", "key_usage", "key_permissions")


def _is_implicit(index) -> bool:
    """True for an index SQLAlchemy creates from a column's ``index=True``."""
    return bool(getattr(index, "_column_flag", False)) or index.name.startswith("ix_")


def test_no_column_index_is_duplicated_by_an_explicit_index():
    """A column cannot carry both ``index=True`` and its own explicit single-column Index."""
    duplicates: list[tuple[str, str, str]] = []
    for table_name in API_KEYS_TABLES:
        table = Base.metadata.tables[table_name]
        flagged = {column.name for column in table.columns if column.index}
        for index in table.indexes:
            if _is_implicit(index):
                continue
            columns = [expression.name for expression in index.expressions if hasattr(expression, "name")]
            if len(columns) == 1 and columns[0] in flagged:
                duplicates.append((table_name, index.name, columns[0]))

    assert duplicates == []
