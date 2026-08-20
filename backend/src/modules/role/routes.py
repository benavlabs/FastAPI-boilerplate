from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from fastcrud import PaginatedListResponse, compute_offset, paginated_response

from ...infrastructure.auth.http_exceptions import ForbiddenException, NotFoundException
from ...infrastructure.dependencies import AsyncSessionDep
from ..common.exceptions import PermissionDeniedError, ResourceExistsError, RoleNotFoundError, ValidationError
from ..common.utils.error_handler import handle_exception
from .dependencies import RoleServiceDep, require_permissions
from .permissions import PermissionNames, flatten_permission_tree
from .schemas import RoleCreate, RolePermissionCreate, RoleRead, RoleUpdate, UserRoleCreate

router = APIRouter(tags=["Roles"])

RequireRoleRead = Annotated[dict[str, Any], Depends(require_permissions(PermissionNames.role_read))]
RequireRoleCreate = Annotated[dict[str, Any], Depends(require_permissions(PermissionNames.role_create))]
RequireRoleUpdate = Annotated[dict[str, Any], Depends(require_permissions(PermissionNames.role_update))]
RequireRoleDelete = Annotated[dict[str, Any], Depends(require_permissions(PermissionNames.role_delete))]
RequireRoleAssign = Annotated[dict[str, Any], Depends(require_permissions(PermissionNames.role_assign))]


@router.get("/permissions", response_model=list[str], summary="List permission tree (flat)")
async def list_permissions() -> list[str]:
    """Return every permission name from the code-defined tree."""
    return flatten_permission_tree()


@router.get("/", response_model=PaginatedListResponse[RoleRead], summary="List roles")
async def list_roles(
    db: AsyncSessionDep,
    role_service: RoleServiceDep,
    _user: RequireRoleRead,
    page: int = 1,
    items_per_page: int = 10,
) -> dict:
    try:
        data = await role_service.get_all(db=db, skip=compute_offset(page, items_per_page), limit=items_per_page)
        return paginated_response(crud_data=data, page=page, items_per_page=items_per_page)
    except PermissionDeniedError as e:
        raise ForbiddenException(str(e))
    except Exception as e:
        http_exception = handle_exception(e)
        if http_exception:
            raise http_exception
        raise HTTPException(status_code=500, detail="An unexpected error occurred")


@router.post("/", response_model=RoleRead, status_code=201, summary="Create a role")
async def create_role(
    role: RoleCreate,
    db: AsyncSessionDep,
    role_service: RoleServiceDep,
    _user: RequireRoleCreate,
) -> dict[str, Any]:
    try:
        return await role_service.create(role, db)
    except ResourceExistsError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except PermissionDeniedError as e:
        raise ForbiddenException(str(e))
    except Exception as e:
        http_exception = handle_exception(e)
        if http_exception:
            raise http_exception
        raise HTTPException(status_code=500, detail="An unexpected error occurred")


@router.get("/{role_id}", response_model=RoleRead, summary="Get a role")
async def get_role(
    role_id: int,
    db: AsyncSessionDep,
    role_service: RoleServiceDep,
    _user: RequireRoleRead,
) -> dict[str, Any]:
    try:
        return await role_service.get_by_id(role_id, db)
    except RoleNotFoundError:
        raise NotFoundException("Role not found")
    except Exception as e:
        http_exception = handle_exception(e)
        if http_exception:
            raise http_exception
        raise HTTPException(status_code=500, detail="An unexpected error occurred")


@router.patch("/{role_id}", summary="Update a role")
async def update_role(
    role_id: int,
    role_update: RoleUpdate,
    db: AsyncSessionDep,
    role_service: RoleServiceDep,
    _user: RequireRoleUpdate,
) -> dict[str, str]:
    try:
        await role_service.update(role_id, role_update, db)
        return {"message": "Role updated"}
    except RoleNotFoundError:
        raise NotFoundException("Role not found")
    except ResourceExistsError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        http_exception = handle_exception(e)
        if http_exception:
            raise http_exception
        raise HTTPException(status_code=500, detail="An unexpected error occurred")


@router.delete("/{role_id}", summary="Soft-delete a role")
async def delete_role(
    role_id: int,
    db: AsyncSessionDep,
    role_service: RoleServiceDep,
    _user: RequireRoleDelete,
) -> dict[str, str]:
    try:
        await role_service.soft_delete(role_id, db)
        return {"message": "Role deleted"}
    except RoleNotFoundError:
        raise NotFoundException("Role not found")
    except Exception as e:
        http_exception = handle_exception(e)
        if http_exception:
            raise http_exception
        raise HTTPException(status_code=500, detail="An unexpected error occurred")


@router.post("/{role_id}/permissions", status_code=201, summary="Assign a permission to a role")
async def assign_permission(
    role_id: int,
    body: RolePermissionCreate,
    db: AsyncSessionDep,
    role_service: RoleServiceDep,
    _user: RequireRoleUpdate,
) -> dict[str, Any]:
    payload = RolePermissionCreate(role_id=role_id, permission_name=body.permission_name)
    try:
        return await role_service.assign_permission(payload, db)
    except (RoleNotFoundError, ValidationError, ResourceExistsError) as e:
        status = 404 if isinstance(e, RoleNotFoundError) else 400
        raise HTTPException(status_code=status, detail=str(e))
    except Exception as e:
        http_exception = handle_exception(e)
        if http_exception:
            raise http_exception
        raise HTTPException(status_code=500, detail="An unexpected error occurred")


@router.post("/assignments", status_code=201, summary="Assign a role to a user")
async def assign_user_role(
    body: UserRoleCreate,
    db: AsyncSessionDep,
    role_service: RoleServiceDep,
    _user: RequireRoleAssign,
) -> dict[str, Any]:
    try:
        return await role_service.assign_role(body, db)
    except (RoleNotFoundError, ResourceExistsError) as e:
        status = 404 if isinstance(e, RoleNotFoundError) else 409
        raise HTTPException(status_code=status, detail=str(e))
    except Exception as e:
        http_exception = handle_exception(e)
        if http_exception:
            raise http_exception
        raise HTTPException(status_code=500, detail="An unexpected error occurred")