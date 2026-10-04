"""Mixins for SQLAdmin views to handle dataclass-based models."""

from collections.abc import AsyncGenerator
from datetime import date, time, timedelta
from decimal import Decimal
from typing import Any

from sqladmin.helpers import Writer, secure_filename, stream_to_csv
from starlette.requests import Request
from starlette.responses import StreamingResponse

SPREADSHEET_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")
NUMERIC_CELL_TYPES = (int, float, Decimal, date, time, timedelta)


def as_spreadsheet_text(value: Any) -> str:
    """Render ``value`` for a CSV cell, prefixing formula-like text with an apostrophe.

    ``None``, numbers, dates and times render as sqladmin renders them. Any other
    value whose text starts with ``=``, ``+``, ``-``, ``@``, a tab or a carriage
    return gets the apostrophe.
    """
    cell = str(value)
    if value is None or isinstance(value, NUMERIC_CELL_TYPES):
        return cell

    return f"'{cell}" if cell.startswith(SPREADSHEET_FORMULA_PREFIXES) else cell


class TextCsvExportMixin:
    """Mixin for SQLAdmin ModelView that writes formula-like CSV cells as text.

    Covers both export paths: ``export_data`` for the plain CSV, and
    ``custom_export_cell`` for the one ``use_pretty_export`` takes. JSON exports go
    to sqladmin unchanged.

    Usage:
        class MyAdmin(TextCsvExportMixin, ModelView, model=MyModel):
            can_export = True
    """

    async def export_data(self, data: list[Any], export_type: str = "csv") -> StreamingResponse:
        """Stream ``data`` as CSV, or hand any other format to sqladmin."""
        if export_type != "csv":
            return await super().export_data(data, export_type=export_type)  # type: ignore[misc,no-any-return]

        if self.use_pretty_export:  # type: ignore[attr-defined]
            return await super().export_data(data, export_type=export_type)  # type: ignore[misc,no-any-return]

        names = self.get_export_columns()  # type: ignore[attr-defined]

        async def generate(writer: Writer) -> AsyncGenerator[Any, None]:
            yield writer.writerow(names)

            for row in data:
                cells = [as_spreadsheet_text(await self.get_prop_value(row, name)) for name in names]  # type: ignore[attr-defined]
                yield writer.writerow(cells)

        filename = secure_filename(self.get_export_name(export_type="csv"))  # type: ignore[attr-defined]

        return StreamingResponse(
            content=stream_to_csv(generate),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f"attachment;filename={filename}"},
        )

    async def custom_export_cell(self, row: Any, name: str, value: Any) -> str | None:
        """Return the pretty export's cell for ``name``, as text where ``value`` looks like a formula."""
        cell = await super().custom_export_cell(row, name, value)  # type: ignore[misc]
        if cell is not None:
            return as_spreadsheet_text(cell)

        if as_spreadsheet_text(value) == str(value):
            return None

        _, formatted = await self.get_list_value(row, name)  # type: ignore[attr-defined]

        return as_spreadsheet_text(formatted)


class DataclassModelMixin:
    """Mixin for SQLAdmin ModelView to support dataclass-based SQLAlchemy models.

    SQLAdmin's default insert_model creates an empty model instance via model(),
    then sets attributes. This fails for MappedAsDataclass models with required
    fields that have no defaults.

    This mixin overrides insert_model to create the model WITH the form data,
    which works correctly with dataclass __init__ signatures.

    Usage:
        class MyAdmin(DataclassModelMixin, ModelView, model=MyModel):
            ...

        # For custom data transformation before model creation:
        class UserAdmin(DataclassModelMixin, ModelView, model=User):
            async def on_model_change(self, data, model, is_created, request):
                if is_created:
                    # Transform data BEFORE model is created
                    data["hashed_password"] = hash(data.pop("password"))
    """

    async def insert_model(self, request: Request, data: dict[str, Any]) -> Any:
        """Create model instance with data for dataclass compatibility.

        Instead of creating an empty model then setting attributes,
        we create the model with all data at once, which satisfies
        dataclass required field constraints.
        """
        await self.on_model_change(data, None, True, request)  # type: ignore[attr-defined]

        clean_data = {}
        for key, value in data.items():
            if hasattr(self, "_mapper") and key in self._mapper.relationships:
                rel = self._mapper.relationships[key]
                if rel.direction.name == "MANYTOONE":
                    fk_columns = list(rel.local_columns)
                    if fk_columns:
                        fk_col_name = fk_columns[0].name
                        clean_data[fk_col_name] = int(value) if value else None
                continue

            if value == "" and hasattr(self, "_mapper"):
                col = self._mapper.columns.get(key)
                if col is not None and col.nullable:
                    value = None

            clean_data[key] = value

        obj = self.model(**clean_data)  # type: ignore[attr-defined]

        async with self.session_maker(expire_on_commit=False) as session:  # type: ignore[attr-defined]
            session.add(obj)
            await session.commit()
            await session.refresh(obj)
            await self.after_model_change(data, obj, True, request)  # type: ignore[attr-defined]
            return obj
