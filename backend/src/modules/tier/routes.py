from typing import Any

from fastapi import APIRouter
from fastcrud import PaginatedListResponse, compute_offset, paginated_response

from ...infrastructure.auth.deps import CurrentPrincipalDep, CurrentSuperUserDep, CurrentUserDep
from ...infrastructure.dependencies import AsyncSessionDep
from ..common.pagination import ItemsPerPageDep, PageDep
from ..user.dependencies import UserServiceDep
from .dependencies import TierServiceDep
from .schemas import TierRead, UserTierUpdate

router = APIRouter(tags=["Tiers"])
user_tier_router = APIRouter(tags=["Tiers"])


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
    page: PageDep = 1,
    items_per_page: ItemsPerPageDep = 10,
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


@user_tier_router.get(
    "/{username}/tier",
    summary="Get User Subscription Tier",
    description="""
            Retrieves detailed information about a user's subscription tier.

            This endpoint returns comprehensive data about the user's current
            subscription tier, including name, features, limitations, and any
            custom configurations.

            Permission rules:
            - Users can view their own tier information
            - Administrators can view any user's tier information

            This is useful for displaying subscription information to users
            or for determining available features in client applications.
            """,
    responses={
        200: {"description": "Tier information retrieved"},
        403: {"description": "Not authorized to view this tier information"},
        404: {"description": "User not found"},
    },
    response_description="User profile with detailed tier information",
)
async def get_user_tier(
    username: str,
    db: AsyncSessionDep,
    current_user: CurrentUserDep,
    principal: CurrentPrincipalDep,
    user_service: UserServiceDep,
    tier_service: TierServiceDep,
) -> dict[str, Any]:
    """Get detailed tier information for a user."""
    await user_service.verify_user_permission(
        current_user, username, "view tier information", is_superuser=principal.is_superuser
    )

    user = await user_service.get_by_username(username, db)
    return await tier_service.get_for_user(user["id"], db)


@user_tier_router.patch(
    "/{username}/tier",
    summary="Update User Subscription Tier (Admin)",
    description="""
            Changes a user's subscription tier.

            This admin-only endpoint allows changing which subscription tier
            a user is assigned to. This affects the user's:
            - API rate limits
            - Available features
            - Access privileges

            When a user's tier is changed, all related configurations (such as
            rate limits) are automatically updated based on the new tier's settings.
            """,
    responses={
        200: {"description": "User tier updated successfully"},
        400: {"description": "Invalid tier ID"},
        403: {"description": "Not authorized - requires admin privileges"},
        404: {"description": "User not found or tier not found"},
    },
    response_description="Success confirmation message",
)
async def update_user_tier(
    username: str,
    values: UserTierUpdate,
    db: AsyncSessionDep,
    user_service: UserServiceDep,
    tier_service: TierServiceDep,
    _: CurrentSuperUserDep,
) -> dict[str, str]:
    """Update a user's subscription tier (admin only)."""
    user = await user_service.get_by_username(username, db)
    await tier_service.update_user_tier(user["id"], values, db)
    return {"message": "User tier updated successfully"}
