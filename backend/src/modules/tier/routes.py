from typing import Any

from fastapi import APIRouter
from fastcrud import PaginatedListResponse, compute_offset, paginated_response

from ...infrastructure.dependencies import AsyncSessionDep, CurrentUserDep
from .dependencies import TierServiceDep
from .schemas import TierRead

router = APIRouter(tags=["Tiers"])


@router.get(
    "/",
    response_model=PaginatedListResponse[TierRead],
    summary="List tiers",
    responses={401: {"description": "Not authenticated"}},
)
async def get_tiers(
    db: AsyncSessionDep,
    _: CurrentUserDep,
    tier_service: TierServiceDep,
    page: int = 1,
    items_per_page: int = 10,
) -> dict:
    """Paginated list of tiers (authenticated)."""
    tiers_data = await tier_service.get_all(
        db=db,
        skip=compute_offset(page, items_per_page),
        limit=items_per_page,
    )
    return paginated_response(crud_data=tiers_data, page=page, items_per_page=items_per_page)


@router.get(
    "/{name}",
    response_model=TierRead,
    summary="Get a tier by name",
    responses={
        401: {"description": "Not authenticated"},
        404: {"description": "Tier not found"},
    },
)
async def get_tier_by_name(
    name: str,
    db: AsyncSessionDep,
    _: CurrentUserDep,
    tier_service: TierServiceDep,
) -> dict[str, Any]:
    """Get a tier by name (authenticated)."""
    return await tier_service.get_by_name(name, db)
