"""API endpoints for API key management."""

from typing import Any

from fastapi import APIRouter, Path, Query
from fastcrud import PaginatedListResponse, compute_offset, paginated_response

from ...infrastructure.dependencies import AsyncSessionDep, CurrentUserDep
from .dependencies import APIKeyServiceDep
from .schemas import (
    APIKeyCreate,
    APIKeyRead,
    APIKeyUpdate,
    KeyUsageRead,
)

router = APIRouter(tags=["API Keys"])


@router.post(
    "/",
    status_code=201,
    summary="Create API Key",
    description="""
    Creates a new API key for the authenticated user.

    API keys enable programmatic access to the API and are useful
    for building developer-facing products and integrations.

    - **name**: Human-readable name for the API key
    - **permissions**: Permission settings for the key
    - **usage_limits**: Usage limits specific to this key
    - **expires_at**: Optional expiration date

    ⚠️ **Important**: The full API key is only shown once during creation.
    Store it securely as it cannot be retrieved again.
    """,
    responses={
        201: {"description": "API key created successfully"},
        400: {"description": "Invalid API key data"},
        401: {"description": "Authentication required"},
    },
    response_description="Created API key with full key (shown only once)",
)
async def create_api_key(
    key_data: APIKeyCreate,
    current_user: CurrentUserDep,
    api_key_service: APIKeyServiceDep,
    db: AsyncSessionDep,
) -> dict[str, Any]:
    """Create a new API key for the authenticated user."""
    return await api_key_service.create_api_key(
        user_id=current_user["id"] if isinstance(current_user, dict) else current_user.id,
        key_data=key_data,
        db=db,
    )


@router.get(
    "/",
    response_model=PaginatedListResponse[APIKeyRead],
    summary="Get User API Keys",
    description="""
    Retrieves all API keys for the authenticated user.

    - **active_only**: Whether to return only active keys (default: true)
    - **page**: Page number (default: 1)
    - **items_per_page**: Items per page (default: 50)

    Returns keys sorted by creation date (newest first).
    For security, only the key prefix is shown, not the full key.
    """,
    responses={
        200: {"description": "API keys retrieved successfully"},
        401: {"description": "Authentication required"},
    },
    response_description="Paginated list of user's API keys",
)
async def get_user_api_keys(
    current_user: CurrentUserDep,
    api_key_service: APIKeyServiceDep,
    db: AsyncSessionDep,
    active_only: bool = Query(True, description="Return only active keys"),
    page: int = Query(1, ge=1, description="Page number"),
    items_per_page: int = Query(50, ge=1, le=100, description="Items per page"),
) -> dict[str, Any]:
    """Get all API keys for the authenticated user."""
    result = await api_key_service.get_user_api_keys(
        user_id=current_user["id"] if isinstance(current_user, dict) else current_user.id,
        active_only=active_only,
        limit=items_per_page,
        offset=compute_offset(page, items_per_page),
        db=db,
    )

    return paginated_response(
        crud_data=result,
        page=page,
        items_per_page=items_per_page,
    )


@router.get(
    "/{key_id}",
    summary="Get API Key Details",
    description="""
    Retrieves details for a specific API key.

    - **key_id**: ID of the API key to retrieve

    Users can only access their own API keys.
    Returns comprehensive key information including usage limits and permissions.
    """,
    responses={
        200: {"description": "API key details retrieved successfully"},
        401: {"description": "Authentication required"},
        403: {"description": "Access denied to this API key"},
        404: {"description": "API key not found"},
    },
    response_description="API key details",
)
async def get_api_key(
    current_user: CurrentUserDep,
    api_key_service: APIKeyServiceDep,
    db: AsyncSessionDep,
    key_id: int = Path(..., description="API key ID"),
) -> dict[str, Any]:
    """Get details for a specific API key."""
    return await api_key_service.get_api_key(
        key_id=key_id,
        user_id=current_user["id"] if isinstance(current_user, dict) else current_user.id,
        db=db,
    )


@router.patch(
    "/{key_id}",
    summary="Update API Key",
    description="""
    Updates an existing API key.

    - **key_id**: ID of the API key to update

    Allows updating name, permissions, usage limits, active status, and expiration.
    Users can only update their own API keys.
    """,
    responses={
        200: {"description": "API key updated successfully"},
        400: {"description": "Invalid update data"},
        401: {"description": "Authentication required"},
        403: {"description": "Access denied to this API key"},
        404: {"description": "API key not found"},
    },
    response_description="Updated API key details",
)
async def update_api_key(
    update_data: APIKeyUpdate,
    current_user: CurrentUserDep,
    api_key_service: APIKeyServiceDep,
    db: AsyncSessionDep,
    key_id: int = Path(..., description="API key ID"),
) -> dict[str, Any]:
    """Update an existing API key."""
    return await api_key_service.update_api_key(
        key_id=key_id,
        user_id=current_user["id"] if isinstance(current_user, dict) else current_user.id,
        update_data=update_data,
        db=db,
    )


@router.delete(
    "/{key_id}",
    status_code=204,
    summary="Delete API Key",
    description="""
    Deletes (deactivates) an API key.

    - **key_id**: ID of the API key to delete

    This operation deactivates the key rather than permanently deleting it
    to maintain usage history and audit trails.

    Users can only delete their own API keys.
    """,
    responses={
        204: {"description": "API key deleted successfully"},
        401: {"description": "Authentication required"},
        403: {"description": "Access denied to this API key"},
        404: {"description": "API key not found"},
    },
)
async def delete_api_key(
    current_user: CurrentUserDep,
    api_key_service: APIKeyServiceDep,
    db: AsyncSessionDep,
    key_id: int = Path(..., description="API key ID"),
) -> None:
    """Delete (deactivate) an API key."""
    await api_key_service.delete_api_key(
        key_id=key_id,
        user_id=current_user["id"] if isinstance(current_user, dict) else current_user.id,
        db=db,
    )


@router.get(
    "/{key_id}/usage",
    response_model=PaginatedListResponse[KeyUsageRead],
    summary="Get API Key Usage History",
    description="""
    Retrieves usage history for a specific API key.

    - **key_id**: ID of the API key
    - **page**: Page number (default: 1)
    - **items_per_page**: Items per page (default: 100)

    Returns usage records in reverse chronological order (newest first).
    Includes details like endpoints used, response times, costs, and errors.
    """,
    responses={
        200: {"description": "Usage history retrieved successfully"},
        401: {"description": "Authentication required"},
        403: {"description": "Access denied to this API key"},
        404: {"description": "API key not found"},
    },
    response_description="Paginated list of usage records",
)
async def get_key_usage(
    current_user: CurrentUserDep,
    api_key_service: APIKeyServiceDep,
    db: AsyncSessionDep,
    key_id: int = Path(..., description="API key ID"),
    page: int = Query(1, ge=1, description="Page number"),
    items_per_page: int = Query(100, ge=1, le=1000, description="Items per page"),
) -> dict[str, Any]:
    """Get usage history for an API key."""
    result = await api_key_service.get_key_usage(
        key_id=key_id,
        user_id=current_user["id"] if isinstance(current_user, dict) else current_user.id,
        limit=items_per_page,
        offset=compute_offset(page, items_per_page),
        db=db,
    )

    return paginated_response(
        crud_data=result,
        page=page,
        items_per_page=items_per_page,
    )


@router.get(
    "/{key_id}/analytics",
    summary="Get API Key Usage Analytics",
    description="""
    Retrieves comprehensive usage analytics for a specific API key.

    - **key_id**: ID of the API key
    - **days**: Number of days to analyze (default: 30)

    Returns detailed analytics including:
    - Total and successful request counts
    - Token usage and costs
    - Average response times
    - Most used endpoints
    - Error breakdown
    """,
    responses={
        200: {"description": "Analytics retrieved successfully"},
        401: {"description": "Authentication required"},
        403: {"description": "Access denied to this API key"},
        404: {"description": "API key not found"},
    },
    response_description="Usage analytics for the API key",
)
async def get_key_analytics(
    current_user: CurrentUserDep,
    api_key_service: APIKeyServiceDep,
    db: AsyncSessionDep,
    key_id: int = Path(..., description="API key ID"),
    days: int = Query(30, ge=1, le=365, description="Number of days to analyze"),
) -> dict[str, Any]:
    """Get usage analytics for an API key."""
    return await api_key_service.get_usage_analytics(
        key_id=key_id,
        user_id=current_user["id"] if isinstance(current_user, dict) else current_user.id,
        days=days,
        db=db,
    )


@router.get(
    "/summary/user",
    summary="Get User API Key Summary",
    description="""
    Retrieves a comprehensive summary of all API keys for the authenticated user.

    Includes:
    - Total and active key counts
    - Overall usage statistics
    - Total costs across all keys
    - List of all keys with basic information

    This endpoint provides a dashboard-style overview of the user's API key usage.
    """,
    responses={
        200: {"description": "User summary retrieved successfully"},
        401: {"description": "Authentication required"},
    },
    response_description="Comprehensive API key summary for the user",
)
async def get_user_summary(
    current_user: CurrentUserDep,
    api_key_service: APIKeyServiceDep,
    db: AsyncSessionDep,
) -> dict[str, Any]:
    """Get comprehensive API key summary for the authenticated user."""
    return await api_key_service.get_user_summary(
        user_id=current_user["id"] if isinstance(current_user, dict) else current_user.id,
        db=db,
    )
