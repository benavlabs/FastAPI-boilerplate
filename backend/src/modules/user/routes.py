from typing import Any

from crudauth.utils import canonical_email
from fastapi import APIRouter, Request
from fastcrud import PaginatedListResponse, compute_offset, paginated_response

from ...infrastructure.auth.authorization import load_permissions, require_permissions
from ...infrastructure.auth.deps import CurrentPermissionsDep, CurrentSuperUserDep, CurrentUserDep
from ...infrastructure.auth.password_attempts import count_password_attempt
from ...infrastructure.dependencies import AsyncSessionDep
from ..common.pagination import ItemsPerPageDep, PageDep
from .dependencies import UserServiceDep
from .schemas import (
    UserCreate,
    UserProfileRead,
    UserRead,
    UserSelfUpdate,
)

router = APIRouter(tags=["Users"])


@router.post(
    "/",
    status_code=201,
    response_model=UserRead,
    summary="Create New User Account",
    description="""
           Creates a new user account in the system.

           This endpoint allows registration of new users with their basic information:
           - Full name
           - Username (must be lowercase alphanumeric)
           - Email address
           - Password (with security requirements)

           New accounts are automatically assigned to the default tier.
           """,
    responses={
        201: {"description": "User account created successfully"},
        400: {"description": "Invalid user data"},
        409: {"description": "Username or email already exists"},
    },
    response_description="The created user profile with assigned ID",
)
async def create_user(
    user: UserCreate,
    db: AsyncSessionDep,
    user_service: UserServiceDep,
) -> dict[str, Any]:
    """Create a new user account."""
    return await user_service.create(user, db)


@router.get(
    "/",
    response_model=PaginatedListResponse[UserRead],
    summary="List All Users",
    description="""
           Retrieves a paginated list of all users in the system.

           Requires the `user.read` permission, which a role grants; superusers
           always pass. The results include basic profile information for each
           user.

           For security reasons, sensitive information like passwords is never included
           in the response.
           """,
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Not authorized - requires the user.read permission"},
    },
    response_description="A paginated list of users with total count and pagination metadata",
    dependencies=[require_permissions("user.read")],
)
async def get_users(
    db: AsyncSessionDep,
    user_service: UserServiceDep,
    page: PageDep = 1,
    items_per_page: ItemsPerPageDep = 10,
) -> dict[str, Any]:
    """Get paginated list of users."""
    users_data = await user_service.get_paginated(skip=compute_offset(page, items_per_page), limit=items_per_page, db=db)

    return paginated_response(crud_data=users_data, page=page, items_per_page=items_per_page)


@router.get(
    "/me",
    response_model=UserRead,
    summary="Get Current User Profile",
    description="""
            Retrieves the profile information of the currently authenticated user.

            This endpoint provides users with their own profile data including:
            - Basic profile information (name, username, email)
            - Profile image URL
            - Subscription tier information
            - Authentication details (superuser status, email verification)

            This is a convenient way for frontend applications to get the current
            user's information for display or personalization purposes.
            """,
    responses={401: {"description": "Not authenticated"}},
    response_description="The current user's profile data",
)
async def get_current_user_profile(
    current_user: CurrentUserDep,
) -> dict[str, Any]:
    """Get current authenticated user's profile."""
    return current_user


@router.get(
    "/{username}",
    response_model=UserProfileRead,
    summary="Get User Profile by Username",
    description="""
            Retrieves a user's public profile by their unique username.

            Any signed-in user can look up any other active user. The response carries
            the display fields only - no email address - so the lookup can't be used to
            collect addresses. Read your own full record from `/users/me`.

            Note that usernames are case-sensitive in lookup operations.
            """,
    responses={401: {"description": "Not authenticated"}, 404: {"description": "User not found"}},
    response_description="The requested user's profile data",
)
async def get_user_by_username(
    username: str,
    _: CurrentUserDep,
    db: AsyncSessionDep,
    user_service: UserServiceDep,
) -> dict[str, Any]:
    """Get user profile by username."""
    user = await user_service.get_by_username(username, db)
    return user


@router.get(
    "/active-and-inactive/{username}",
    response_model=UserRead,
    summary="Get Active and Inactive User Profile by Username(Admin)",
    description="""
            Retrieve a user's profile information by their unique username.

            This endpoint can be used to look up any user in the system by their
            username. It returns the same profile data structure as other user
            endpoints but does not include sensitive information.

            Note that usernames are case-sensitive in lookup operations.
            """,
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Not authorized - requires admin privileges"},
        404: {"description": "User not found"},
    },
    response_description="the requested user's profile data",
)
async def get_active_and_inactive_user_by_username(
    username: str,
    db: AsyncSessionDep,
    _: CurrentSuperUserDep,
    user_service: UserServiceDep,
) -> dict[str, Any]:
    """Get active and inactive profile by username."""
    return await user_service.get_active_and_inactive_by_username(username, db)


@router.patch(
    "/{username}",
    summary="Update User Profile",
    description="""
            Updates a user's profile information.

            This endpoint allows users to modify their own profile data, and users
            holding the `user.update` permission to modify another user's data. Only
            the fields provided in the request will be updated, and all fields are
            optional.

            Permission rules:
            - Regular users can only update their own profiles
            - Superusers can update any user's profile
            - A `user.update` holder can update another user only when that user is
              not a superuser and holds no permission the requester lacks, and cannot
              change another user's email address
            - Note: Tier updates are handled by a separate endpoint (/users/{username}/tier)

            Changing your own email address requires `current_password` in the body,
            and clears the address's verified status. A wrong or missing password answers
            403. Every change that needs the password counts against the same budget as
            `POST /api/v1/auth/change-password`, right ones included: 5 per hour per
            account, then 429. A superuser changing another account's address needs no
            password and counts nothing. An account that signs in with a provider can't
            change its address at all.

            Username and email changes are validated to ensure uniqueness.
            """,
    responses={
        200: {"description": "Profile updated successfully"},
        400: {"description": "Invalid profile data"},
        403: {"description": "Not authorized to update this profile, or the email change was not confirmed"},
        429: {"description": "Too many password attempts"},
        404: {"description": "User not found"},
        409: {"description": "Username or email already exists"},
    },
    response_description="Success confirmation message",
)
async def update_user_profile(
    username: str,
    values: UserSelfUpdate,
    request: Request,
    current_user: CurrentUserDep,
    permissions: CurrentPermissionsDep,
    db: AsyncSessionDep,
    user_service: UserServiceDep,
) -> dict[str, str]:
    """Update user profile information."""
    await user_service.verify_update_permission(current_user, username, permissions)
    user = await user_service.get_by_username(username, db)

    if not user_service.is_self_or_superuser(current_user, user["username"]):
        target_permissions = await load_permissions(db, user["id"])
        user_service.verify_no_privilege_escalation(user, values, permissions, target_permissions)

    changes_email = values.email is not None and canonical_email(values.email) != user["email"]
    if changes_email and user_service.email_change_needs_password(current_user, user["id"]):
        await count_password_attempt(request, current_user["id"])

    await user_service.update(user["id"], values, db, requester=current_user, current_password=values.current_password)
    return {"message": "User updated successfully"}


@router.delete(
    "/{username}",
    summary="Deactivate User Account",
    description="""
            Soft-deletes (deactivates) a user account.

            This endpoint performs a logical deletion of a user account, marking it
            as deactivated in the system rather than permanently removing it. This allows
            for potential reactivation in the future.

            Permission rules:
            - Regular users can only deactivate their own accounts
            - Administrators can deactivate any user's account

            Deactivated accounts cannot be used for login and are typically hidden
            from regular user listings.
            """,
    responses={
        200: {"description": "Account deactivated successfully"},
        403: {"description": "Not authorized to deactivate this account"},
        404: {"description": "User not found"},
    },
    response_description="Success confirmation message",
)
async def delete_user_account(
    username: str,
    current_user: CurrentUserDep,
    db: AsyncSessionDep,
    user_service: UserServiceDep,
) -> dict[str, str]:
    """Soft delete a user account."""
    await user_service.verify_user_permission(current_user, username, "delete this account")
    user = await user_service.get_by_username(username, db)

    await user_service.delete(user["id"], db)
    return {"message": "User account deactivated"}


@router.delete(
    "/db/{username}",
    summary="GDPR Delete User (Admin)",
    description="""
            GDPR/LGPD compliant user deletion with data anonymization.

            This admin-only endpoint anonymizes user PII while preserving business data
            integrity and maintaining referential relationships for conversations and
            analytics data.

            This operation:
            - Removes personally identifiable information (PII)
            - Retains email for legal compliance purposes
            - Prevents future login by clearing credentials
            - Maintains foreign key relationships (conversations, logs)
            - Logs the deletion event with legal basis for audit compliance

            Unlike hard deletion, this approach:
            - Complies with GDPR Article 17 (Right to Erasure)
            - Preserves business analytics data
            - Eliminates foreign key constraint violations
            - Maintains audit trails for legal requirements

            This operation is needed for:
            - GDPR/LGPD data deletion requests
            - Legal compliance while preserving business data
            - Safe user removal without breaking referential integrity
            """,
    responses={
        200: {"description": "User anonymized successfully"},
        403: {"description": "Not authorized - requires admin privileges"},
        404: {"description": "User not found"},
    },
    response_description="Success confirmation message",
)
async def gdpr_delete_user(
    username: str,
    db: AsyncSessionDep,
    user_service: UserServiceDep,
    _: CurrentSuperUserDep,
) -> dict[str, str]:
    """GDPR compliant user anonymization (admin only)."""
    user = await user_service.get_active_and_inactive_by_username(username, db)
    await user_service.anonymize_user(user["id"], db)
    return {"message": "User data anonymized in compliance with GDPR"}
