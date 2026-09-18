from typing import Any

from fastcrud.types import GetMultiResponseDict
from sqlalchemy.ext.asyncio import AsyncSession

from ..common.exceptions import PermissionDeniedError, ResourceExistsError, TierNotFoundError, ValidationError
from ..rate_limit.crud import crud_rate_limits
from ..user.crud import crud_users
from .crud import crud_tiers
from .schemas import (
    TierCreate,
    TierCreateInternal,
    TierRead,
    TierUpdate,
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
            raise ResourceExistsError("Failed to create tier")
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

        if await crud_rate_limits.exists(db=db, tier_id=tier["id"]):
            raise ValidationError(
                f"Cannot delete tier '{tier['name']}' because it has rate limits. Delete the rate limits first."
            )

    async def verify_superuser(self, user: dict[str, Any], action: str = "manage tiers") -> None:
        """Verify that a user has superuser privileges."""
        if not user.get("is_superuser", False):
            raise PermissionDeniedError(f"Only superusers can {action}")
