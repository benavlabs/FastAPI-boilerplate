from typing import Any

from fastapi import APIRouter
from fastcrud import PaginatedListResponse, compute_offset, paginated_response

from ...infrastructure.dependencies import AsyncSessionDep, CurrentSuperUserDep
from .dependencies import RateLimitServiceDep
from .schemas import (
    RateLimitRead,
    RateLimitUpdate,
)

router = APIRouter(tags=["Rate Limits"])


@router.get(
    "/",
    response_model=PaginatedListResponse[RateLimitRead],
    summary="List All Rate Limits",
    description="""
           Retrieves a paginated list of all rate limits defined in the system.

           This endpoint provides information about the API rate limits configured
           for different subscription tiers. Each rate limit defines:
           - The API path it applies to
           - The maximum number of requests allowed (limit)
           - The time period in seconds for the limit (period)
           - The tier it belongs to

           Results are paginated to handle systems with many rate limit configurations.
           """,
    responses={401: {"description": "Not authenticated"}},
    response_description="A paginated list of rate limits with their configuration details",
)
async def get_rate_limits(
    db: AsyncSessionDep,
    rate_limit_service: RateLimitServiceDep,
    page: int = 1,
    items_per_page: int = 10,
) -> dict[str, Any]:
    """
    Get a paginated list of all rate limits.
    This endpoint is available to all authenticated users.
    """
    rate_limits_data = await rate_limit_service.get_all(
        db=db,
        skip=compute_offset(page, items_per_page),
        limit=items_per_page,
    )

    return paginated_response(crud_data=rate_limits_data, page=page, items_per_page=items_per_page)


@router.get(
    "/{name}",
    response_model=RateLimitRead,
    summary="Get Active Rate Limit Details",
    description="""
           Retrieves detailed information about a specific rate limit by name.

           This endpoint returns configuration details for a single rate limit,
           identified by its unique name. The response includes:
           - The API path it applies to
           - The maximum number of requests allowed (limit)
           - The time period in seconds for the limit (period)
           - The tier it belongs to

           Rate limit names are typically in the format of `path:limit:period`.
           """,
    responses={401: {"description": "Not authenticated"}, 404: {"description": "Rate limit not found"}},
    response_description="Detailed configuration of the requested rate limit",
)
async def get_rate_limit(
    name: str,
    db: AsyncSessionDep,
    rate_limit_service: RateLimitServiceDep,
) -> dict[str, Any] | None:
    """
    Get detailed information about a specific rate limit by name.
    This endpoint is available to all authenticated users.
    """
    rate_limit = await rate_limit_service.get_by_name(name, db)
    return rate_limit


@router.patch(
    "/{name}",
    summary="Update Rate Limit (Admin)",
    description="""
           Updates an existing rate limit configuration.

           This admin-only endpoint allows modifying the properties of a rate limit
           identified by its unique name. The following properties can be updated:
           - API path: The endpoint pattern to apply the limit to
           - Limit: Maximum number of requests allowed in the period
           - Period: Time window in seconds for the limit
           - Name: The identifier of the rate limit

           Only the fields provided in the request will be updated. Omitted fields
           will retain their current values.

           Note that updating a rate limit immediately affects all users in the
           associated tier.
           """,
    responses={
        200: {"description": "Rate limit updated successfully"},
        400: {"description": "Invalid rate limit data"},
        403: {"description": "Not authorized - requires admin privileges"},
        404: {"description": "Rate limit not found"},
        409: {"description": "New rate limit name already exists"},
    },
    response_description="Success confirmation message",
)
async def update_rate_limit(
    name: str,
    values: RateLimitUpdate,
    db: AsyncSessionDep,
    rate_limit_service: RateLimitServiceDep,
    _: CurrentSuperUserDep,
) -> dict[str, str]:
    """
    Update an existing rate limit.
    This endpoint is restricted to superusers only.
    """
    await rate_limit_service.update(name, values, db)
    return {"message": "Rate limit updated"}


@router.delete(
    "/{name}",
    summary="Permanent Delete Rate Limit (Admin)",
    description="""
            Permanently removes a rate limit configuration from the system.

            This admin-only endpoint allows deletion of a rate limit identified
            by its unique name. Deleting a rate limit will immediately affect all
            users in the associated tier.

            Once a rate limit is deleted, the API endpoints previously governed
            by that limit will fall back to either:
            - Another less specific rate limit configuration for the same tier
            - The default system-wide rate limit configuration

            Use this endpoint with caution, as removing rate limits could potentially
            allow users to make unlimited requests to certain API endpoints.
            """,
    responses={
        200: {"description": "Rate limit deleted successfully"},
        403: {"description": "Not authorized - requires admin privileges"},
        404: {"description": "Rate limit not found"},
    },
    response_description="Success confirmation message",
)
async def delete_rate_limit(
    name: str,
    db: AsyncSessionDep,
    rate_limit_service: RateLimitServiceDep,
    _: CurrentSuperUserDep,
) -> dict[str, str]:
    """
    Delete a rate limit.
    This endpoint is restricted to superusers only.
    """
    await rate_limit_service.delete(name, db)
    return {"message": "Rate limit deleted"}
