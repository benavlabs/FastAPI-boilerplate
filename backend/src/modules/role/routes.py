"""Managing roles, and reading the permissions this project has.

Every route is gated by its own ``role.*`` permission, and the ones that hand out
access additionally run the escalation checks in ``delegation``: a caller can neither
grant a permission nor assign a role carrying one unless they hold it themselves.
Superusers pass both.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from fastcrud import PaginatedListResponse, compute_offset, paginated_response

from ...infrastructure.auth.authorization import get_current_permissions, require_permissions
from ...infrastructure.auth.deps import CurrentPrincipalDep, CurrentUserDep
from ...infrastructure.dependencies import AsyncSessionDep
from ...infrastructure.permissions import permission_groups
from ..common.pagination import ItemsPerPageDep, PageDep
from .dependencies import RoleServiceDep
from .permissions import RolePermissionName
from .schemas import RoleCreate, RolePermissions, RoleRead, RoleUpdate

permissions_router = APIRouter(tags=["Permissions"])
router = APIRouter(tags=["Roles"])
user_roles_router = APIRouter(tags=["Roles"])


@permissions_router.get(
    "",
    summary="List Every Registered Permission",
    description="""
            Every permission the running project has, grouped by the resource that
            declared it.

            This is what a UI offers when it builds a role: the names are the only ones
            a role may carry, since a grant for anything else is ignored wherever
            permissions are checked.
            """,
    responses={401: {"description": "Not authenticated"}},
    response_description="The registered permission names, by resource",
)
async def list_permissions(_: CurrentUserDep) -> dict[str, dict[str, list[str]]]:
    """Every registered permission name, grouped by resource."""
    return {"permissions": {resource: list(names) for resource, names in sorted(permission_groups().items())}}


@permissions_router.get(
    "/me",
    summary="List the Caller's Own Permissions",
    description="""
            The permissions the caller effectively holds, gathered from every source the
            project wired: their roles today, plus whatever else a feature contributes.

            A superuser holds every registered permission. A name that is no longer
            registered is left out, so a stale grant never appears here.
            """,
    responses={401: {"description": "Not authenticated"}},
    response_description="The caller's effective permission names",
)
async def list_my_permissions(
    permissions: Annotated[frozenset[str], Depends(get_current_permissions)],
) -> dict[str, list[str]]:
    """The permission names the caller holds."""
    return {"permissions": sorted(permissions)}


@router.get(
    "/",
    response_model=PaginatedListResponse[RoleRead],
    summary="List Roles",
    description="""
            A page of the roles this project has, each with the permissions it carries.
            """,
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Missing the role.read permission"},
    },
    dependencies=[require_permissions(RolePermissionName.READ.value)],
    response_description="A page of roles",
)
async def list_roles(
    db: AsyncSessionDep,
    _: CurrentUserDep,
    role_service: RoleServiceDep,
    page: PageDep = 1,
    items_per_page: ItemsPerPageDep = 10,
) -> dict[str, Any]:
    """A page of roles."""
    roles = await role_service.get_all(db=db, skip=compute_offset(page, items_per_page), limit=items_per_page)

    return paginated_response(crud_data=roles, page=page, items_per_page=items_per_page)


@router.get(
    "/{role_id}",
    response_model=RoleRead,
    summary="Get a Role",
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Missing the role.read permission"},
        404: {"description": "Role not found"},
    },
    dependencies=[require_permissions(RolePermissionName.READ.value)],
    response_description="The role and the permissions it carries",
)
async def get_role(role_id: int, db: AsyncSessionDep, _: CurrentUserDep, role_service: RoleServiceDep) -> dict[str, Any]:
    """One role, with the permissions it carries."""
    return await role_service.get(role_id, db)


@router.post(
    "/",
    response_model=RoleRead,
    status_code=201,
    summary="Create a Role",
    description="""
            Creates a role carrying the permissions named in the body.

            Only registered permission names are accepted, and a caller may only hand out
            permissions they hold themselves: a role carrying anything else answers 403 and
            nothing is written. Superusers may grant anything.
            """,
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Missing the role.create permission, or granting what the caller doesn't hold"},
        409: {"description": "A role with this name already exists"},
        422: {"description": "An unknown permission name"},
    },
    dependencies=[require_permissions(RolePermissionName.CREATE.value)],
    response_description="The role that was created",
)
async def create_role(
    values: RoleCreate,
    db: AsyncSessionDep,
    principal: CurrentPrincipalDep,
    role_service: RoleServiceDep,
) -> dict[str, Any]:
    """Create a role carrying the permissions it was given."""
    return await role_service.create(values.name, values.description, values.permissions, principal, db)


@router.patch(
    "/{role_id}",
    response_model=RoleRead,
    summary="Rename a Role",
    description="""
            Changes a role's name or description. What it carries is set through
            `PUT /api/v1/roles/{role_id}/permissions`.

            A caller may only relabel a role whose permissions they hold themselves, so a
            role stronger than the caller cannot be renamed into something it isn't.
            """,
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Missing the role.update permission, or relabelling a stronger role"},
        404: {"description": "Role not found"},
        409: {"description": "A role with this name already exists"},
    },
    dependencies=[require_permissions(RolePermissionName.UPDATE.value)],
    response_description="The role as it now stands",
)
async def update_role(
    role_id: int,
    values: RoleUpdate,
    db: AsyncSessionDep,
    principal: CurrentPrincipalDep,
    role_service: RoleServiceDep,
) -> dict[str, Any]:
    """Change a role's name or description."""
    return await role_service.update(role_id, values.model_dump(exclude_unset=True), principal, db)


@router.put(
    "/{role_id}/permissions",
    response_model=RoleRead,
    summary="Set What a Role Carries",
    description="""
            Replaces the permissions a role carries with the ones in the body.

            A caller may only hand out permissions they hold themselves, and may only take
            away permissions they hold: a change that touches anything else answers 403 and
            nothing is written. Superusers may set anything.
            """,
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Missing the role.update permission, or touching what the caller doesn't hold"},
        404: {"description": "Role not found"},
        422: {"description": "An unknown permission name"},
    },
    dependencies=[require_permissions(RolePermissionName.UPDATE.value)],
    response_description="The role and what it now carries",
)
async def set_role_permissions(
    role_id: int,
    values: RolePermissions,
    db: AsyncSessionDep,
    principal: CurrentPrincipalDep,
    role_service: RoleServiceDep,
) -> dict[str, Any]:
    """Replace the permissions a role carries."""
    return await role_service.set_permissions(role_id, values.permissions, principal, db)


@router.delete(
    "/{role_id}",
    summary="Delete a Role",
    description="""
            Deletes a role, and with it every assignment of it.

            A caller may only delete a role whose permissions they hold themselves.
            """,
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Missing the role.delete permission, or deleting what the caller doesn't hold"},
        404: {"description": "Role not found"},
    },
    dependencies=[require_permissions(RolePermissionName.DELETE.value)],
    response_description="Success confirmation message",
)
async def delete_role(
    role_id: int,
    db: AsyncSessionDep,
    principal: CurrentPrincipalDep,
    role_service: RoleServiceDep,
) -> dict[str, str]:
    """Delete a role."""
    await role_service.delete(role_id, principal, db)

    return {"message": "Role deleted"}


@router.post(
    "/{role_id}/users/{user_id}",
    status_code=201,
    summary="Assign a Role",
    description="""
            Gives an account a role.

            A caller may only assign a role whose permissions they hold themselves, and may
            only change the roles of an account that is not a superuser and holds nothing
            they don't hold: a role cannot be used to hand out more access than the caller
            has, in either direction. Assigning a role the account already holds changes
            nothing and still answers 201.
            """,
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Missing the role.assign permission, or reaching a role or an account the caller cannot"},
        404: {"description": "Role or user not found"},
    },
    dependencies=[require_permissions(RolePermissionName.ASSIGN.value)],
    response_description="Success confirmation message",
)
async def assign_role(
    role_id: int,
    user_id: int,
    db: AsyncSessionDep,
    principal: CurrentPrincipalDep,
    role_service: RoleServiceDep,
) -> dict[str, str]:
    """Give an account a role."""
    await role_service.assign(role_id, user_id, principal, db)

    return {"message": "Role assigned"}


@router.delete(
    "/{role_id}/users/{user_id}",
    summary="Unassign a Role",
    description="""
            Takes a role away from an account, under the same rule as assigning it.
            """,
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Missing the role.assign permission, or reaching a role or an account the caller cannot"},
        404: {"description": "Role or user not found"},
    },
    dependencies=[require_permissions(RolePermissionName.ASSIGN.value)],
    response_description="Success confirmation message",
)
async def unassign_role(
    role_id: int,
    user_id: int,
    db: AsyncSessionDep,
    principal: CurrentPrincipalDep,
    role_service: RoleServiceDep,
) -> dict[str, str]:
    """Take a role away from an account."""
    await role_service.unassign(role_id, user_id, principal, db)

    return {"message": "Role unassigned"}


@user_roles_router.get(
    "/{user_id}/roles",
    response_model=list[RoleRead],
    summary="List a User's Roles",
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Missing the role.read permission"},
        404: {"description": "User not found"},
    },
    dependencies=[require_permissions(RolePermissionName.READ.value)],
    response_description="The roles the account holds",
)
async def list_user_roles(
    user_id: int, db: AsyncSessionDep, _: CurrentUserDep, role_service: RoleServiceDep
) -> list[dict[str, Any]]:
    """The roles an account holds."""
    return await role_service.roles_of(user_id, db)
