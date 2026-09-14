from typing import Any

from fastapi import APIRouter, HTTPException
from fastcrud import PaginatedListResponse, compute_offset, paginated_response

from ...infrastructure.auth.http_exceptions import NotFoundException
from ...infrastructure.dependencies import AsyncSessionDep, CurrentUserDep
from ..common.exceptions import TierNotFoundError
from ..common.utils.error_handler import handle_exception
from .dependencies import TierServiceDep
from .schemas import TierRead

router = APIRouter(tags=["Tiers"])


@router.get("/", response_model=PaginatedListResponse[TierRead], summary="List tiers")
async def get_tiers(
    db: AsyncSessionDep,
    _: CurrentUserDep,
    tier_service: TierServiceDep,
    page: int = 1,
    items_per_page: int = 10,
) -> dict:
    """Paginated list of tiers."""
    try:
        tiers_data = await tier_service.get_all(
            db=db,
            skip=compute_offset(page, items_per_page),
            limit=items_per_page,
        )
        return paginated_response(crud_data=tiers_data, page=page, items_per_page=items_per_page)
    except Exception as e:
        http_exception = handle_exception(e)
        if http_exception:
            raise http_exception
        raise HTTPException(status_code=500, detail="An unexpected error occurred")


@router.get("/{name}", response_model=TierRead, summary="Get a tier by name")
async def get_tier_by_name(
    name: str,
    db: AsyncSessionDep,
    _: CurrentUserDep,
    tier_service: TierServiceDep,
) -> dict[str, Any]:
    """Get a tier by name."""
    try:
        return await tier_service.get_by_name(name, db)
    except TierNotFoundError:
        raise NotFoundException("Tier not found")
    except Exception as e:
        http_exception = handle_exception(e)
        if http_exception:
            raise http_exception
        raise HTTPException(status_code=500, detail="An unexpected error occurred")
