"""The page bounds every listing shares."""

from typing import Annotated

from fastapi import Query

MAX_ITEMS_PER_PAGE = 100

PageDep = Annotated[int, Query(ge=1, description="Page number")]
ItemsPerPageDep = Annotated[int, Query(ge=1, le=MAX_ITEMS_PER_PAGE, description=f"Items per page (max {MAX_ITEMS_PER_PAGE})")]
