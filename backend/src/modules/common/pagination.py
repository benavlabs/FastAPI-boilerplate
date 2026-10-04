"""The page bounds every listing shares, and the range an integer key covers."""

from typing import Annotated

from fastapi import Query

MAX_ITEMS_PER_PAGE = 100
MAX_PAGE = 2**31 - 1
MAX_INTEGER_ID = 2**31 - 1

PageDep = Annotated[int, Query(ge=1, le=MAX_PAGE, description="Page number")]
ItemsPerPageDep = Annotated[int, Query(ge=1, le=MAX_ITEMS_PER_PAGE, description=f"Items per page (max {MAX_ITEMS_PER_PAGE})")]
