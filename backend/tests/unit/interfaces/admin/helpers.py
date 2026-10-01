"""Reading back what an admin view's CSV export streams."""

import csv
from typing import Any


async def exported_rows(view: Any, rows: list[Any]) -> list[list[str]]:
    """Return the parsed lines of ``view``'s CSV export of ``rows``, header first."""
    response = await view.export_data(rows, export_type="csv")
    streamed = [chunk async for chunk in response.body_iterator]
    text = "".join(chunk.decode() if isinstance(chunk, bytes) else chunk for chunk in streamed)

    return list(csv.reader(text.splitlines()))
