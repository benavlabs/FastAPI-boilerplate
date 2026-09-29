import uuid
from datetime import UTC, datetime
from typing import Any

from fastcrud import JoinConfig
from fastcrud.types import GetMultiResponseDict
from sqlalchemy.ext.asyncio import AsyncSession

from ..common.exceptions import (
    PermissionDeniedError,
    PersistenceError,
    ResourceExistsError,
)
from ..tier.crud import crud_tiers
from ..tier.exceptions import TierNotFoundError
from ..tier.models import Tier
from ..tier.schemas import TierRead
from ..user.crud import crud_users
from ..user.exceptions import UserNotFoundError
from ..user.models import User
from ..user.schemas import UserRead
from .crud import crud_rate_limits
from .exceptions import RateLimitNotFoundError
from .models import RateLimit
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
            raise PersistenceError("Rate limit row was not returned after insert")
        return created_rate_limit

    async def get_all(self, db: AsyncSession, skip: int = 0, limit: int = 100) -> GetMultiResponseDict:
        """Get all rate limits with pagination."""
        return await crud_rate_limits.get_multi(
            db=db, offset=skip, limit=limit, schema_to_select=RateLimitRead, is_deleted=False, sort_columns="id"
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

    async def get_for_user(self, user_id: int, db: AsyncSession) -> dict[str, Any]:
        """Get rate limits for a user through their tier assignment.

        Retrieves all rate limits applicable to a user based on their tier
        assignment. Uses database joins for efficient data retrieval.

        Args:
            user_id: ID of the user to get rate limits for.
            db: Database session for the operation.

        Returns:
            Dictionary containing user data with nested rate limits.

        Raises:
            UserNotFoundError: If the user doesn't exist.

        Note:
            Rate limits are inherited from the user's tier. Users without
            tier assignments have no rate limits. Uses advanced joins to
            efficiently retrieve related data.

        Example:
            ```python
            user_limits = await service.get_rate_limits(123, db)
            for limit in user_limits.get("rate_limits", []):
                print(f"Rate limit: {limit['resource']} - {limit['limit']}")
            ```
        """
        user = await crud_users.get(db=db, id=user_id, is_deleted=False, schema_to_select=UserRead)
        if not user:
            raise UserNotFoundError(f"User with ID {user_id} not found")

        if user["tier_id"] is None:
            user["rate_limits"] = []
            return user

        joins_config = [
            JoinConfig(
                model=Tier,
                join_on=User.tier_id == Tier.id,
                join_prefix="tier_",
                schema_to_select=TierRead,
                join_type="left",
            ),
            JoinConfig(
                model=RateLimit,
                join_on=Tier.id == RateLimit.tier_id,
                join_prefix="rate_limits_",
                schema_to_select=RateLimitRead,
                join_type="left",
                relationship_type="one-to-many",
            ),
        ]

        result = await crud_users.get_joined(
            db=db, schema_to_select=UserRead, joins_config=joins_config, nest_joins=True, id=user_id
        )

        if not result:
            raise UserNotFoundError(f"User with ID {user_id} not found")

        return result
