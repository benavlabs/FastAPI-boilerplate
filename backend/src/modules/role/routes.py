"""Reading the permissions this project has, and the ones the caller holds."""

from typing import Annotated

from fastapi import APIRouter, Depends

from ...infrastructure.auth.authorization import get_current_permissions
from ...infrastructure.auth.deps import CurrentUserDep
from ...infrastructure.permissions import permission_groups

permissions_router = APIRouter(tags=["Permissions"])


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
