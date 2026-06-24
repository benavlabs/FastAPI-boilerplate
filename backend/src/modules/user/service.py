from datetime import UTC, datetime
from typing import Any, cast

from crudauth import get_password_hash
from fastcrud import JoinConfig
from fastcrud.types import GetMultiResponseDict
from sqlalchemy.exc import MultipleResultsFound, NoResultFound
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.logging import get_logger
from ..common.exceptions import PermissionDeniedError, TierNotFoundError, UserExistsError, UserNotFoundError, ValidationError
from ..rate_limit.models import RateLimit
from ..rate_limit.schemas import RateLimitRead
from ..tier.crud import crud_tiers
from ..tier.models import Tier
from ..tier.schemas import TierRead
from .crud import crud_users
from .models import User
from .schemas import (
    User as UserSchema,
)
from .schemas import (
    UserAnonymize,
    UserCreate,
    UserCreateInternal,
    UserRead,
    UserTierUpdate,
    UserUpdate,
)

logger = get_logger()


class UserService:
    """Service class for user-related operations.

    This service manages user accounts including creation, updates, authentication,
    tier management, and permission handling. It provides comprehensive user
    management functionality with support for soft deletion, tier-based access
    control, and rate limiting through tier associations.
    """

    async def create(self, user: UserCreate, db: AsyncSession) -> dict[str, Any]:
        """Create a new user account.

        Creates a new user with unique email and username validation. Automatically
        hashes the password and stores user credentials securely.

        Args:
            user: User creation data including email, username, and password.
            db: Database session for the operation.

        Returns:
            The created user data dictionary.

        Raises:
            UserExistsError: If email or username already exists.

        Note:
            Passwords are automatically hashed using secure password hashing.
            Both email and username must be unique across the system.

        Example:
            ```python
            user_data = UserCreate(
                email="user@example.com",
                username="johndoe",
                password="securepassword123"
            )
            created_user = await service.create(user_data, db)
            ```
        """
        email_exists = await crud_users.exists(db=db, email=user.email)
        if email_exists:
            raise UserExistsError("Email already registered")

        username_exists = await crud_users.exists(db=db, username=user.username)
        if username_exists:
            raise UserExistsError("Username already taken")

        user_internal_dict = user.model_dump()
        user_internal_dict["hashed_password"] = get_password_hash(password=user_internal_dict["password"])
        del user_internal_dict["password"]

        user_internal = UserCreateInternal(**user_internal_dict)
        created_user = await crud_users.create(db=db, object=user_internal, schema_to_select=UserRead)
        if not created_user:
            raise UserExistsError("Failed to create user")
        return created_user

    async def get_paginated(self, db: AsyncSession, skip: int = 0, limit: int = 100) -> GetMultiResponseDict:
        """Retrieve a paginated list of users.

        Gets users with pagination support, excluding soft-deleted accounts.
        Useful for administrative interfaces and user management.

        Args:
            db: Database session for the operation.
            skip: Number of records to skip for pagination.
            limit: Maximum number of records to return.

        Returns:
            Dictionary containing paginated user data with metadata.

        Raises:
            ValueError: If database session is None.

        Note:
            Only returns non-deleted users (is_deleted=False).
            Returns data in format: {"data": [...], "count": int, "has_more": bool}

        Example:
            ```python
            users = await service.get_paginated(skip=0, limit=20, db=db)
            for user in users["data"]:
                print(f"User: {user['username']} - {user['email']}")
            ```
        """
        if db is None:
            raise ValueError("Database session cannot be None")

        return await crud_users.get_multi(
            db=db,
            offset=skip,
            limit=limit,
            schema_to_select=UserRead,
            is_deleted=False,
        )

    async def get_by_username(self, username: str, db: AsyncSession) -> dict[str, Any]:
        """Retrieve a user by username.

        Finds a user by their unique username, excluding soft-deleted accounts.

        Args:
            username: Username to search for.
            db: Database session for the operation.

        Returns:
            User data dictionary if found.

        Raises:
            UserNotFoundError: If no user exists with the given username.

        Note:
            Only returns non-deleted users. Usernames are unique identifiers
            commonly used for authentication and user references.

        Example:
            ```python
            user = await service.get_by_username("johndoe", db)
            print(f"User email: {user['email']}")
            ```
        """
        user = await crud_users.get(
            db=db,
            schema_to_select=UserRead,
            username=username,
            is_deleted=False,
        )
        if not user:
            raise UserNotFoundError(f"User with username '{username}' not found")
        return user

    async def get_active_and_inactive_by_username(self, username: str, db: AsyncSession) -> dict[str, Any]:
        """Retrieve a user by username.

        Finds a user by their username, including soft-deleted accounts.

        Args:
            username: Username to search for.
            db: Database session for the operation.

        Returns:
            User data dictionary if found.

        Note:
            Usernames are unique identifiers commonly used for authentication and user references.

        Example:
            ```python
            user = await service.get_active_and_inactive_by_username("johndoe", db)
            print(f"User email: {user['email']}")
            ```
        """
        user = await crud_users.get(db=db, schema_to_select=UserRead, username=username)
        if not user:
            raise UserNotFoundError(f"User with username '{username}' not found")
        return user

    async def get_by_email(self, email: str, db: AsyncSession) -> dict[str, Any]:
        """Retrieve a user by email address.

        Finds a user by their unique email address, excluding soft-deleted accounts.
        Returns the user model instance for authentication purposes.

        Args:
            email: Email address to search for.
            db: Database session for the operation.

        Returns:
            User data dictionary if found.

        Raises:
            UserNotFoundError: If no user exists with the given email.

        Note:
            Only returns non-deleted users. Email addresses are unique identifiers
            primarily used for authentication and account recovery.

        Example:
            ```python
            user = await service.get_by_email("user@example.com", db)
            print(f"User ID: {user['id']}")
            ```
        """
        user = await crud_users.get(
            db=db,
            schema_to_select=UserRead,
            email=email,
            is_deleted=False,
        )
        if not user:
            raise UserNotFoundError(f"User with email '{email}' not found")
        return user

    async def update(self, user_id: int, user_update: UserUpdate, db: AsyncSession) -> dict[str, Any]:
        """Update user information.

        Updates user fields with validation for unique constraints on email
        and username. Only provided fields are updated.

        Args:
            user_id: ID of the user to update.
            user_update: Fields to update with new values.
            db: Database session for the operation.

        Returns:
            Updated user data dictionary.

        Raises:
            UserNotFoundError: If the user doesn't exist.
            UserExistsError: If email or username conflicts with existing users.

        Note:
            Validates uniqueness when updating email or username.
            Only non-deleted users can be updated.

        Example:
            ```python
            update_data = UserUpdate(
                email="newemail@example.com",
                first_name="John"
            )
            updated_user = await service.update(123, update_data, db)
            ```
        """
        existing_user = await crud_users.get(db=db, id=user_id, is_deleted=False)
        if not existing_user:
            raise UserNotFoundError(f"User with ID {user_id} not found")

        update_data = user_update.model_dump(exclude_unset=True)

        if "email" in update_data and update_data["email"] != existing_user["email"]:
            email_exists = await crud_users.exists(db=db, email=update_data["email"])
            if email_exists:
                raise UserExistsError("Email already registered")

        if "username" in update_data and update_data["username"] != existing_user["username"]:
            username_exists = await crud_users.exists(db=db, username=update_data["username"])
            if username_exists:
                raise UserExistsError("Username already taken")

        updated_user = await crud_users.update(
            db=db, object=user_update, id=user_id, return_columns=list(UserSchema.model_fields.keys())
        )
        if not updated_user:
            raise UserNotFoundError(f"User with ID {user_id} not found")
        return updated_user

    async def check_update_permission(self, requester_user: dict[str, Any], target_username: str) -> bool:
        """Check if user has permission to update another user.

        Determines if the requesting user has permission to update the target user.
        Superusers can update any user, regular users can only update themselves.

        Args:
            requester_user: User data of the user making the request.
            target_username: Username of the user to be updated.

        Returns:
            True if the user has permission, False otherwise.

        Note:
            Permission rules:
            - Superusers can update any user
            - Regular users can only update their own profile
        """
        if requester_user.get("is_superuser", False):
            return True

        return requester_user.get("username") == target_username

    async def verify_user_permission(
        self, requester_user: dict[str, Any], target_username: str, action_description: str = "perform this action"
    ) -> None:
        """Verify user has permission to perform an action on another user.

        Checks permissions and raises an exception if the user doesn't have
        the required permissions for the specified action.

        Args:
            requester_user: User data of the user making the request.
            target_username: Username of the user to perform action on.
            action_description: Description of the action for error messages.

        Raises:
            PermissionDeniedError: If the user doesn't have permission.

        Note:
            This method combines permission checking with error handling
            for convenient use in API endpoints and business logic.

        Example:
            ```python
            await service.verify_user_permission(
                current_user, "johndoe", "update profile"
            )
            ```
        """
        has_permission = await self.check_update_permission(requester_user, target_username)
        if not has_permission:
            raise PermissionDeniedError(f"You don't have permission to {action_description} on this user")

    async def delete(self, user_id: int, db: AsyncSession) -> None:
        """Soft delete a user.

        Marks a user as deleted without removing them from the database.
        This preserves data integrity while making the user inaccessible.

        Args:
            user_id: ID of the user to soft delete.
            db: Database session for the operation.

        Raises:
            UserNotFoundError: If the user doesn't exist.
            ValidationError: If multiple users found with same ID.

        Note:
            Soft deletion preserves user data for audit purposes while
            preventing login and making the user invisible in normal queries.
        """
        try:
            await crud_users.delete(db=db, id=user_id)
        except NoResultFound:
            raise UserNotFoundError(f"User with ID {user_id} not found")
        except MultipleResultsFound:
            raise ValidationError("Multiple users found with same ID")

    async def permanent_delete(self, user_id: int, db: AsyncSession) -> None:
        """Permanently delete a user from the database.

        Completely removes a user from the database. This operation cannot
        be undone and should be used with extreme caution.

        Args:
            user_id: ID of the user to permanently delete.
            db: Database session for the operation.

        Raises:
            UserNotFoundError: If the user doesn't exist.
            ValidationError: If multiple users found with same ID.

        Note:
            This is a destructive operation that removes all user data.
            Consider using soft deletion instead for most use cases.
        """
        try:
            await crud_users.db_delete(db=db, id=user_id)
        except NoResultFound:
            raise UserNotFoundError(f"User with ID {user_id} not found")
        except MultipleResultsFound:
            raise ValidationError("Multiple users found with same ID")

    async def anonymize_user(self, user_id: int, db: AsyncSession) -> None:
        """GDPR/LGPD compliant user anonymization.

        Anonymizes user PII while preserving the user record and email for legal purposes.
        Maintains referential integrity with conversations and other related data.

        This method:
        1. Removes all personally identifiable information (PII)
        2. Keeps email and timestamps for documented legal compliance
        3. Prevents future login by clearing password
        4. Maintains foreign key relationships intact
        5. Marks user as deleted with soft deletion

        Args:
            user_id: ID of the user to anonymize.
            db: Database session for the operation.

        Raises:
            UserNotFoundError: If the user doesn't exist.

        Note:
            This satisfies GDPR Article 17 (Right to Erasure) requirements while
            preserving business data integrity. User conversations, analytics data,
            and audit trails remain intact with anonymized user references.

            Email is retained for documented legal purposes (tax, AML, etc.)
            as permitted under GDPR Article 17(3)(b).

        Example:
            ```python
            # GDPR compliant deletion
            await service.anonymize_user(user_id=123, db=db)
            ```
        """
        try:
            existing_user = await crud_users.get(db=db, schema_to_select=UserRead, id=user_id)
            if not existing_user:
                raise UserNotFoundError(f"User with ID {user_id} not found")

            timestamp = int(datetime.now(UTC).timestamp())

            logger.info(
                "User anonymization requested",
                extra={
                    "user_id": user_id,
                    "email": existing_user.get("email"),
                    "action": "user_anonymization_start",
                },
            )

            anonymize_data = UserAnonymize(
                name="[DELETED]",
                username=f"del_{user_id}_{timestamp % 10000}",
                hashed_password="DELETED_INVALID_HASH",
                profile_image_url="https://deleted.com/deleted.jpg",
                tier_id=None,
                is_superuser=False,
                google_id=None,
                github_id=None,
                oauth_provider=None,
                email_verified=False,
                oauth_created_at=None,
                oauth_updated_at=None,
            )

            await crud_users.update(db=db, object=anonymize_data, commit=False, id=user_id)
            await crud_users.delete(db=db, id=user_id)

            anonymized_fields = list(anonymize_data.model_dump(exclude_unset=True).keys())
            logger.info(
                "User anonymization completed",
                extra={
                    "user_id": user_id,
                    "retained_data": ["email", "created_at", "updated_at", "id"],
                    "anonymized_fields": anonymized_fields,
                    "action": "user_anonymization_complete",
                    "foreign_keys_preserved": True,
                },
            )

        except NoResultFound:
            logger.warning(
                "User anonymization failed - user not found",
                extra={"user_id": user_id, "action": "user_anonymization_failed", "reason": "user_not_found"},
            )
            raise UserNotFoundError(f"User with ID {user_id} not found")

    async def update_tier(self, user_id: int, tier_update: UserTierUpdate, db: AsyncSession) -> dict[str, Any]:
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

    async def get_rate_limits(self, user_id: int, db: AsyncSession) -> dict[str, Any]:
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

    async def get_user_with_tier(self, user_id: int, db: AsyncSession) -> dict[str, Any]:
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
