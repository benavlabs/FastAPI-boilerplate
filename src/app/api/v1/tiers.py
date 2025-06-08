from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, Request
from fastcrud.paginated import PaginatedListResponse, compute_offset, paginated_response
from sqlalchemy.ext.asyncio import AsyncSession

from ...api.dependencies import get_current_superuser
from ...core.db.database import async_get_db
from ...core.exceptions.http_exceptions import DuplicateValueException, NotFoundException
from ...crud.crud_tier import crud_tiers
from ...schemas.tier import TierCreate, TierCreateInternal, TierRead, TierUpdate

router = APIRouter(tags=["tiers"])


@router.post("/tier", dependencies=[Depends(get_current_superuser)], status_code=201)
async def write_tier(
    request: Request, tier: TierCreate, db: Annotated[AsyncSession, Depends(async_get_db)]
) -> TierRead:
    tier_internal_dict = tier.model_dump()
    db_tier = await crud_tiers.exists(db=db, name=tier_internal_dict["name"])
    if db_tier:
        raise DuplicateValueException("Tier Name not available")

    tier_internal = TierCreateInternal(**tier_internal_dict)
    created_tier = await crud_tiers.create(db=db, object=tier_internal)

    tier_read = await crud_tiers.get(db=db, id=created_tier.id, schema_to_select=TierRead)
    if tier_read is None:
        raise NotFoundException("Created tier not found")

    return cast(TierRead, tier_read)


@router.get("/tiers", response_model=PaginatedListResponse[TierRead])
async def read_tiers(
    request: Request, db: Annotated[AsyncSession, Depends(async_get_db)], page: int = 1, items_per_page: int = 10
) -> dict:
    tiers_data = await crud_tiers.get_multi(db=db, offset=compute_offset(page, items_per_page), limit=items_per_page)

    response: dict[str, Any] = paginated_response(crud_data=tiers_data, page=page, items_per_page=items_per_page)
    return response


@router.get("/tier/{name}", response_model=TierRead)
async def read_tier(request: Request, name: str, db: Annotated[AsyncSession, Depends(async_get_db)]) -> TierRead:
    db_tier = await crud_tiers.get(db=db, name=name, schema_to_select=TierRead)
    if db_tier is None:
        raise NotFoundException("Tier not found")

    return cast(TierRead, db_tier)


@router.patch("/tier/{name}", dependencies=[Depends(get_current_superuser)])
async def patch_tier(
    request: Request, name: str, values: TierUpdate, db: Annotated[AsyncSession, Depends(async_get_db)]
) -> dict[str, str]:
    db_tier = await crud_tiers.get(db=db, name=name, schema_to_select=TierRead)
    if db_tier is None:
        raise NotFoundException("Tier not found")

    await crud_tiers.update(db=db, object=values, name=name)
    return {"message": "Tier updated"}


@router.delete("/tier/{name}", dependencies=[Depends(get_current_superuser)])
async def erase_tier(request: Request, name: str, db: Annotated[AsyncSession, Depends(async_get_db)]) -> dict[str, str]:
    db_tier = await crud_tiers.get(db=db, name=name, schema_to_select=TierRead)
    if db_tier is None:
        raise NotFoundException("Tier not found")

    await crud_tiers.delete(db=db, name=name)
    return {"message": "Tier deleted"}
