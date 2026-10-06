from collections.abc import Collection
from datetime import UTC, datetime
from typing import Any

from crudauth import get_password_hash_async
from crudauth.utils import canonical_email
from fastcrud.types import GetMultiResponseDict
from sqlalchemy.exc import MultipleResultsFound, NoResultFound
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.auth.setup import auth
from ...infrastructure.logging import get_logger
from ..common.exceptions import (
    PermissionDeniedError,
    PersistenceError,
    ValidationError,
)
from .crud import crud_users
from .exceptions import (
    UserExistsError,
    UserNotFoundError,
)
from .permissions import UserPermission
from .schemas import (
    User as UserSchema,
)
from .schemas import (
    UserAnonymize,
    UserCreate,
    UserCreateInternal,
    UserRead,
    UserUpdate,
)

logger = get_logger()


class UserService:
    """Service class for user-related operations.

    This service manages user accounts including creation, updates, authentication,
    and permission handling, with support for soft deletion. Features that add to
    the user model bring their own service: the tiers feature owns a user's tier,
    and the tier-limits feature owns the limits that follow from it.

    Addresses are stored as crudauth canonicalises them, which is how it looks an
    account up: a row written in another case could never be signed in to.
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

            Only the four fields above are read from the payload. The verification
            flag and the OAuth identifiers decide which account a provider login
            resolves to, so a password signup always leaves them at their defaults.

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
        await auth.validate_password(user.password, source="register")
        email = canonical_email(user.email)

        email_exists = await crud_users.exists(db=db, email=email)
        if email_exists:
            raise UserExistsError("Email already registered")

        username_exists = await crud_users.exists(db=db, username=user.username)
        if username_exists:
            raise UserExistsError("Username already taken")

        user_internal = UserCreateInternal(
            name=user.name,
            username=user.username,
            email=email,
            hashed_password=await get_password_hash_async(user.password),
        )
        created_user = await crud_users.create(db=db, object=user_internal, schema_to_select=UserRead)
        if not created_user:
            raise PersistenceError("User row was not returned after insert")
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
            sort_columns="id",
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
            email=canonical_email(email),
            is_deleted=False,
        )
        if not user:
            raise UserNotFoundError("No user with that email")
        return user

    async def update(
        self,
        user_id: int,
        user_update: UserUpdate,
        db: AsyncSession,
    ) -> dict[str, Any]:
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
            Validates uniqueness when updating email or username, and an address that
            moves clears ``email_verified``. Only non-deleted users can be updated.

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

        if "email" in update_data:
            update_data["email"] = canonical_email(update_data["email"])

        if "email" in update_data and update_data["email"] != existing_user["email"]:
            email_exists = await crud_users.exists(db=db, email=update_data["email"])
            if email_exists:
                raise UserExistsError("Email already registered")

            update_data["email_verified"] = False

        if "username" in update_data and update_data["username"] != existing_user["username"]:
            username_exists = await crud_users.exists(db=db, username=update_data["username"])
            if username_exists:
                raise UserExistsError("Username already taken")

        updated_user = await crud_users.update(
            db=db, object=update_data, id=user_id, return_columns=list(UserSchema.model_fields.keys())
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

    async def verify_update_permission(
        self,
        requester_user: dict[str, Any],
        target_username: str,
        permissions: Collection[str],
    ) -> None:
        """Verify the requester may update this profile at all.

        Editing your own profile stays the ownership rule. Editing someone else's
        needs the ``user.update`` permission, or superuser.

        Args:
            requester_user: User data of the user making the request.
            target_username: Username of the user to be updated.
            permissions: Effective permissions held by the requester.

        Raises:
            PermissionDeniedError: If the requester may not update this profile.
        """
        if self.is_self_or_superuser(requester_user, target_username):
            return

        if UserPermission.UPDATE.value in permissions:
            return

        raise PermissionDeniedError("You don't have permission to update profile on this user")

    def is_self_or_superuser(self, requester_user: dict[str, Any], target_username: str) -> bool:
        """Whether the requester owns this profile or may act on any of them."""
        if requester_user.get("is_superuser", False):
            return True

        return requester_user.get("username") == target_username

    def verify_no_privilege_escalation(
        self,
        target_user: dict[str, Any],
        values: UserUpdate,
        requester_permissions: Collection[str],
        target_permissions: Collection[str],
    ) -> None:
        """Verify a ``user.update`` holder isn't editing their way to more access.

        Editing an account is a way to take it over, so a non-superuser holding
        ``user.update`` may only edit accounts weaker than their own: not a
        superuser, and holding nothing the requester doesn't already hold.

        Args:
            target_user: The user being updated.
            values: The submitted changes.
            requester_permissions: Effective permissions held by the requester.
            target_permissions: Effective permissions held by the target.

        Raises:
            PermissionDeniedError: If the edit would reach a stronger account.
        """
        if target_user.get("is_superuser", False):
            raise PermissionDeniedError("You don't have permission to update profile on this user")

        if not set(target_permissions) <= set(requester_permissions):
            raise PermissionDeniedError("You don't have permission to update profile on this user")

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
                    "action": "user_anonymization_start",
                },
            )

            anonymized = {
                "name": "[DELETED]",
                "username": f"del_{user_id}_{timestamp % 10000}",
                "hashed_password": "DELETED_INVALID_HASH",
                "profile_image_url": "https://deleted.com/deleted.jpg",
                "is_superuser": False,
                "google_id": None,
                "github_id": None,
                "oauth_provider": None,
                "email_verified": False,
                "oauth_created_at": None,
                "oauth_updated_at": None,
            }
            contributed = dict.fromkeys(UserAnonymize.model_fields.keys() - anonymized.keys())
            anonymize_data = UserAnonymize.model_validate(anonymized | contributed)

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
