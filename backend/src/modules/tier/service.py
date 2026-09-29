from typing import Any, cast

from fastcrud.types import GetMultiResponseDict
from sqlalchemy.ext.asyncio import AsyncSession

from ...wiring.hooks import TIER_DELETE_GUARDS
from ..common.exceptions import (
    PermissionDeniedError,
    PersistenceError,
    ResourceExistsError,
    ValidationError,
)
from ..user.crud import crud_users
from ..user.exceptions import UserNotFoundError
from ..user.schemas import User as UserSchema
from ..user.schemas import UserRead
from .crud import crud_tiers
from .exceptions import TierNotFoundError
from .models import Tier
from .schemas import (
    TierCreate,
    TierCreateInternal,
    TierRead,
    TierUpdate,
    UserTierUpdate,
)


class TierService:
    """Service class for tier-related operations.

    Tiers are bare categorization labels. They have no business logic of their own —
    consumers wire tiers to whatever they need (rate limits, feature flags, billing).
    """

    async def create(self, tier: TierCreate, db: AsyncSession) -> dict[str, Any]:
        """Create a new tier."""
        tier_dict = tier.model_dump()
        if await crud_tiers.exists(db=db, name=tier_dict["name"]):
            raise ResourceExistsError(f"Tier with name '{tier_dict['name']}' already exists")

        tier_internal = TierCreateInternal(**tier_dict)
        created_tier = await crud_tiers.create(db=db, object=tier_internal, schema_to_select=TierRead)
        if not created_tier:
            raise PersistenceError("Tier row was not returned after insert")
        return created_tier

    async def get_all(self, db: AsyncSession, skip: int = 0, limit: int = 100) -> GetMultiResponseDict:
        """Retrieve all tiers with pagination."""
        return await crud_tiers.get_multi(db=db, offset=skip, limit=limit, schema_to_select=TierRead, is_deleted=False)

    async def get_by_id(self, tier_id: int, db: AsyncSession) -> dict[str, Any]:
        """Retrieve a tier by ID."""
        tier = await crud_tiers.get(db=db, id=tier_id, schema_to_select=TierRead, is_deleted=False)
        if not tier:
            raise TierNotFoundError(f"Tier with ID {tier_id} not found")
        return tier

    async def get_by_name(self, name: str, db: AsyncSession) -> dict[str, Any]:
        """Retrieve a tier by name."""
        tier = await crud_tiers.get(db=db, name=name, schema_to_select=TierRead, is_deleted=False)
        if not tier:
            raise TierNotFoundError(f"Tier with name '{name}' not found")
        return tier

    async def update(self, name: str, tier_update: TierUpdate, db: AsyncSession) -> None:
        """Update a tier by name."""
        existing_tier = await crud_tiers.get(db=db, name=name, schema_to_select=TierRead)
        if not existing_tier:
            raise TierNotFoundError(f"Tier with name '{name}' not found")

        update_data = tier_update.model_dump(exclude_unset=True)
        if "name" in update_data and update_data["name"] != name:
            if await crud_tiers.exists(db=db, name=update_data["name"]):
                raise ResourceExistsError(f"Tier with name '{update_data['name']}' already exists")

        await crud_tiers.update(db=db, object=tier_update, name=name)

    async def delete(self, name: str, db: AsyncSession) -> None:
        """Soft delete a tier that no users or rate limits reference."""
        existing_tier = await crud_tiers.get(db=db, name=name, schema_to_select=TierRead, is_deleted=False)
        if not existing_tier:
            raise TierNotFoundError(f"Tier with name '{name}' not found")

        await self._ensure_unreferenced(existing_tier, db)
        await crud_tiers.delete(db=db, name=name)

    async def permanent_delete(self, name: str, db: AsyncSession) -> None:
        """Permanently delete a tier that no users or rate limits reference."""
        existing_tier = await crud_tiers.get(db=db, name=name, schema_to_select=TierRead)
        if not existing_tier:
            raise TierNotFoundError(f"Tier with name '{name}' not found")

        await self._ensure_unreferenced(existing_tier, db)
        await crud_tiers.db_delete(db=db, name=name)

    async def _ensure_unreferenced(self, tier: dict[str, Any], db: AsyncSession) -> None:
        if await crud_users.exists(db=db, tier_id=tier["id"]):
            raise ValidationError(
                f"Cannot delete tier '{tier['name']}' because it is assigned to users. Reassign users to another tier first."
            )

        for guard in TIER_DELETE_GUARDS:
            refusal = await guard(tier, db)
            if refusal is not None:
                raise ValidationError(refusal)

    async def verify_superuser(self, user: dict[str, Any], action: str = "manage tiers") -> None:
        """Verify that a user has superuser privileges."""
        if not user.get("is_superuser", False):
            raise PermissionDeniedError(f"Only superusers can {action}")

    async def update_user_tier(self, user_id: int, tier_update: UserTierUpdate, db: AsyncSession) -> dict[str, Any]:
        """Update a user's tier assignment.

        Changes the tier assignment for a user, which affects their access
        levels, permissions, and rate limits.

        Args:
            user_id: ID of the user to update.
            tier_update: New tier assignment data.
            db: Database session for the operation.

        Returns:
            Updated user data dictionary.

        Raises:
            UserNotFoundError: If the user doesn't exist.
            TierNotFoundError: If the specified tier doesn't exist.

        Note:
            Tier changes immediately affect the user's access levels and
            rate limits. This is typically an administrative operation.

        Example:
            ```python
            tier_update = UserTierUpdate(tier_id=2)
            updated_user = await service.update_tier(123, tier_update, db)
            ```
        """
        existing_user = await crud_users.get(db=db, id=user_id, is_deleted=False)
        if not existing_user:
            raise UserNotFoundError(f"User with ID {user_id} not found")

        tier_exists = await crud_tiers.exists(db=db, id=tier_update.tier_id)
        if not tier_exists:
            raise TierNotFoundError(f"Tier with ID {tier_update.tier_id} not found")

        updated_user = await crud_users.update(
            db=db, object=tier_update, id=user_id, return_columns=list(UserSchema.model_fields.keys())
        )
        if not updated_user:
            raise UserNotFoundError(f"User with ID {user_id} not found")
        return updated_user

    async def get_for_user(self, user_id: int, db: AsyncSession) -> dict[str, Any]:
        """Get user with detailed tier information.

        Retrieves a user along with their complete tier information
        using database joins for efficient data access.

        Args:
            user_id: ID of the user to retrieve.
            db: Database session for the operation.

        Returns:
            Dictionary containing user data with nested tier information.

        Raises:
            UserNotFoundError: If the user doesn't exist.

        Note:
            Returns complete tier details including tier name, description,
            and configuration. Users without tier assignments have tier=None.

        Example:
            ```python
            user_data = await service.get_user_with_tier(123, db)
            if user_data.get("tier"):
                print(f"User tier: {user_data['tier']['name']}")
            ```
        """
        user_dict = await crud_users.get(db=db, id=user_id, is_deleted=False, schema_to_select=UserRead)
        if not user_dict:
            raise UserNotFoundError(f"User with ID {user_id} not found")

        if user_dict.get("tier_id") is None:
            user_dict["tier"] = None
            return user_dict

        tier_exists = await crud_tiers.exists(db=db, id=user_dict["tier_id"])
        if not tier_exists:
            user_dict["tier"] = None
            return user_dict

        result = await crud_users.get_joined(
            db=db,
            join_model=Tier,
            join_prefix="tier_",
            schema_to_select=UserRead,
            join_schema_to_select=TierRead,
            id=user_id,
            nest_joins=True,
        )

        return cast(dict[str, Any], result)
