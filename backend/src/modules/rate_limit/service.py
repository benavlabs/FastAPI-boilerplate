import uuid
from datetime import UTC, datetime
from typing import Any

from fastcrud.types import GetMultiResponseDict
from sqlalchemy.ext.asyncio import AsyncSession

from ..common.exceptions import (
    PermissionDeniedError,
    RateLimitNotFoundError,
    ResourceExistsError,
    TierNotFoundError,
)
from ..tier.crud import crud_tiers
from .crud import crud_rate_limits
from .schemas import (
    RateLimitCreate,
    RateLimitCreateInternal,
    RateLimitRead,
    RateLimitUpdate,
    RateLimitUpdateInternal,
)


class RateLimitService:
    """Service class for rate limit-related operations."""

    async def create(self, rate_limit: RateLimitCreate, tier_id: int, db: AsyncSession) -> dict[str, Any]:
        """Create a new rate limit for a tier."""
        tier_exists = await crud_tiers.exists(db=db, id=tier_id)
        if not tier_exists:
            raise TierNotFoundError(f"Tier with ID {tier_id} not found")

        rate_limit_dict = rate_limit.model_dump()

        if not rate_limit_dict.get("name"):
            unique_id = uuid.uuid4().hex[:6]
            rate_limit_dict["name"] = f"rate_limit_{unique_id}"

        name_exists = await crud_rate_limits.exists(db=db, name=rate_limit_dict["name"])
        if name_exists:
            raise ResourceExistsError(f"Rate limit with name '{rate_limit_dict['name']}' already exists")

        rate_limit_internal = RateLimitCreateInternal(**rate_limit_dict, tier_id=tier_id)
        created_rate_limit = await crud_rate_limits.create(db=db, object=rate_limit_internal, schema_to_select=RateLimitRead)

        if not created_rate_limit:
            raise ResourceExistsError("Failed to create rate limit")
        return created_rate_limit

    async def get_all(self, db: AsyncSession, skip: int = 0, limit: int = 100) -> GetMultiResponseDict:
        """Get all rate limits with pagination."""
        return await crud_rate_limits.get_multi(
            db=db, offset=skip, limit=limit, schema_to_select=RateLimitRead, is_deleted=False
        )

    async def get_by_id(self, rate_limit_id: int, db: AsyncSession) -> dict[str, Any]:
        """Get a rate limit by ID."""
        rate_limit = await crud_rate_limits.get(
            db=db,
            id=rate_limit_id,
            schema_to_select=RateLimitRead,
            is_deleted=False,
        )
        if not rate_limit:
            raise RateLimitNotFoundError(f"Rate limit with ID {rate_limit_id} not found")
        return rate_limit

    async def get_by_name(self, name: str, db: AsyncSession) -> dict[str, Any]:
        """Get an active rate limit by name."""
        rate_limit = await crud_rate_limits.get(
            db=db,
            name=name,
            schema_to_select=RateLimitRead,
            is_deleted=False,
        )
        if not rate_limit:
            raise RateLimitNotFoundError(f"Rate limit with name '{name}' not found")
        return rate_limit

    async def get_active_and_inactive_by_name(self, name: str, db: AsyncSession) -> dict[str, Any]:
        """Get an active or inactive rate limit by name."""
        rate_limit = await crud_rate_limits.get(db=db, name=name, schema_to_select=RateLimitRead)
        if not rate_limit:
            raise RateLimitNotFoundError(f"Rate limit with name '{name}' not found")
        return rate_limit

    async def update(self, name: str, rate_limit_update: RateLimitUpdate, db: AsyncSession) -> None:
        """Update a rate limit by name."""
        existing_rate_limit = await crud_rate_limits.get(db=db, name=name, schema_to_select=RateLimitRead)
        if not existing_rate_limit:
            raise RateLimitNotFoundError(f"Rate limit with name '{name}' not found")

        update_data = rate_limit_update.model_dump(exclude_unset=True)
        if "name" in update_data and update_data["name"] != name:
            name_exists = await crud_rate_limits.exists(db=db, name=update_data["name"])
            if name_exists:
                raise ResourceExistsError(f"Rate limit with name '{update_data['name']}' already exists")

        internal_update = RateLimitUpdateInternal(**update_data, updated_at=datetime.now(UTC))

        await crud_rate_limits.update(db=db, object=internal_update, name=name)

    async def delete(self, name: str, db: AsyncSession) -> None:
        """Permanently delete a rate limit by name."""
        existing_rate_limit = await crud_rate_limits.get(db=db, name=name, schema_to_select=RateLimitRead)
        if not existing_rate_limit:
            raise RateLimitNotFoundError(f"Rate limit with name '{name}' not found")

        await crud_rate_limits.db_delete(db=db, name=name)

    async def verify_superuser(self, user: dict[str, Any], action: str = "manage rate limits") -> None:
        """Verify that the user is a superuser."""
        if not user.get("is_superuser", False):
            raise PermissionDeniedError(f"Only superusers can {action}")
