from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, Request
from fastcrud import PaginatedListResponse, compute_offset, paginated_response
from sqlalchemy.ext.asyncio import AsyncSession

from ...api.dependencies import get_current_superuser, get_current_user
from ...core.authz.casbin import enforcer
from ...core.db.database import async_get_db
from ...core.exceptions.http_exceptions import DuplicateValueException, ForbiddenException, NotFoundException
from ...core.security import blacklist_token, get_password_hash, oauth2_scheme
from ...crud.crud_rate_limit import crud_rate_limits
from ...crud.crud_tier import crud_tiers
from ...crud.crud_users import crud_users
from ...schemas.tier import TierRead
from ...schemas.user import UserCreate, UserCreateInternal, UserRead, UserTierUpdate, UserUpdate

router = APIRouter(tags=["users"])


@router.post("/user", response_model=UserRead, status_code=201)
async def write_user(
    request: Request, user: UserCreate, db: Annotated[AsyncSession, Depends(async_get_db)]
) -> dict[str, Any]:
    email_row = await crud_users.exists(db=db, email=user.email)
    if email_row:
        raise DuplicateValueException("Email is already registered")

    username_row = await crud_users.exists(db=db, username=user.username)
    if username_row:
        raise DuplicateValueException("Username not available")

    user_internal_dict = user.model_dump()
    user_internal_dict["hashed_password"] = get_password_hash(password=user_internal_dict["password"])
    del user_internal_dict["password"]

    user_internal = UserCreateInternal(**user_internal_dict)
    created_user = await crud_users.create(db=db, object=user_internal, schema_to_select=UserRead)

    if created_user is None:
        raise NotFoundException("Failed to create user")

    return created_user


@router.get("/users", response_model=PaginatedListResponse[UserRead])
async def read_users(
    request: Request, db: Annotated[AsyncSession, Depends(async_get_db)], page: int = 1, items_per_page: int = 10
) -> dict:
    users_data = await crud_users.get_multi(
        db=db,
        offset=compute_offset(page, items_per_page),
        limit=items_per_page,
        is_deleted=False,
    )

    response: dict[str, Any] = paginated_response(crud_data=users_data, page=page, items_per_page=items_per_page)
    return response


@router.get("/user/me/", response_model=UserRead)
async def read_users_me(request: Request, current_user: Annotated[dict, Depends(get_current_user)]) -> dict:
    return current_user


@router.get("/user/{username}", response_model=UserRead)
async def read_user(
    request: Request, username: str, db: Annotated[AsyncSession, Depends(async_get_db)]
) -> dict[str, Any]:
    db_user = await crud_users.get(db=db, username=username, is_deleted=False, schema_to_select=UserRead)
    if db_user is None:
        raise NotFoundException("User not found")

    return db_user


@router.patch("/user/{username}")
async def patch_user(
    request: Request,
    values: UserUpdate,
    username: str,
    current_user: Annotated[dict, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(async_get_db)],
) -> dict[str, str]:
    db_user = await crud_users.get(db=db, username=username)
    if db_user is None:
        raise NotFoundException("User not found")

    db_username = db_user["username"]
    db_email = db_user["email"]

    if db_username != current_user["username"]:
        raise ForbiddenException()

    if values.email is not None and values.email != db_email:
        if await crud_users.exists(db=db, email=values.email):
            raise DuplicateValueException("Email is already registered")

    if values.username is not None and values.username != db_username:
        if await crud_users.exists(db=db, username=values.username):
            raise DuplicateValueException("Username not available")

    await crud_users.update(db=db, object=values, username=username)
    return {"message": "User updated"}


@router.delete("/user/{username}")
async def erase_user(
    request: Request,
    username: str,
    current_user: Annotated[dict, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(async_get_db)],
    token: str = Depends(oauth2_scheme),
) -> dict[str, str]:
    db_user = await crud_users.get(db=db, username=username, schema_to_select=UserRead)
    if not db_user:
        raise NotFoundException("User not found")

    if username != current_user["username"]:
        raise ForbiddenException()

    await crud_users.delete(db=db, username=username)
    await blacklist_token(token=token, db=db)
    return {"message": "User deleted"}


@router.delete("/db_user/{username}", dependencies=[Depends(get_current_superuser)])
async def erase_db_user(
    request: Request,
    username: str,
    db: Annotated[AsyncSession, Depends(async_get_db)],
    token: str = Depends(oauth2_scheme),
) -> dict[str, str]:
    db_user = await crud_users.exists(db=db, username=username)
    if not db_user:
        raise NotFoundException("User not found")

    await crud_users.db_delete(db=db, username=username)
    await blacklist_token(token=token, db=db)
    return {"message": "User deleted from the database"}


@router.get("/user/{username}/rate_limits", dependencies=[Depends(get_current_superuser)])
async def read_user_rate_limits(
    request: Request, username: str, db: Annotated[AsyncSession, Depends(async_get_db)]
) -> dict[str, Any]:
    db_user = await crud_users.get(db=db, username=username, schema_to_select=UserRead)
    if db_user is None:
        raise NotFoundException("User not found")

    user_dict = dict(db_user)
    if db_user["tier_id"] is None:
        user_dict["tier_rate_limits"] = []
        return user_dict

    db_tier = await crud_tiers.get(db=db, id=db_user["tier_id"], schema_to_select=TierRead)
    if db_tier is None:
        raise NotFoundException("Tier not found")

    db_rate_limits = await crud_rate_limits.get_multi(db=db, tier_id=db_tier["id"])

    user_dict["tier_rate_limits"] = db_rate_limits["data"]

    return user_dict


@router.get("/user/{username}/tier")
async def read_user_tier(
    request: Request, username: str, db: Annotated[AsyncSession, Depends(async_get_db)]
) -> dict | None:
    db_user = await crud_users.get(db=db, username=username, schema_to_select=UserRead)
    if db_user is None:
        raise NotFoundException("User not found")

    if db_user["tier_id"] is None:
        return None

    db_tier = await crud_tiers.get(db=db, id=db_user["tier_id"], schema_to_select=TierRead)
    if not db_tier:
        raise NotFoundException("Tier not found")

    user_dict = dict(db_user)
    tier_dict = dict(db_tier)

    for key, value in tier_dict.items():
        user_dict[f"tier_{key}"] = value

    return user_dict


@router.patch("/user/{username}/tier", dependencies=[Depends(get_current_superuser)])
async def patch_user_tier(
    request: Request, username: str, values: UserTierUpdate, db: Annotated[AsyncSession, Depends(async_get_db)]
) -> dict[str, str]:
    db_user = await crud_users.get(db=db, username=username, schema_to_select=UserRead)
    if db_user is None:
        raise NotFoundException("User not found")

    db_tier = await crud_tiers.get(db=db, id=values.tier_id, schema_to_select=TierRead)
    if db_tier is None:
        raise NotFoundException("Tier not found")

    await crud_users.update(db=db, object=values.model_dump(), username=username)
    return {"message": f"User {db_user['name']} Tier updated"}


@router.post("/user/{id}/roles", dependencies=[Depends(get_current_superuser)])
async def assign_user_roles(id: str, roles: list[str] = Body(embed=True)) -> dict[str, str]:
    if not enforcer:
         raise NotFoundException("Authorization service not available")

    # 1. Remove existing roles for this user
    # remove_filtered_grouping_policy(field_index, field_value)
    # field_index 0 is the user (g rule: user, role)
    await enforcer.remove_filtered_grouping_policy(0, id)

    # 2. Add new roles
    for role in roles:
        role_name = role if role.startswith("role:") else f"role:{role}"
        await enforcer.add_grouping_policy(id, role_name)

    return {"message": "Roles assigned successfully"}


@router.get("/user/{id}/roles", dependencies=[Depends(get_current_superuser)])
async def get_user_roles(id: str) -> dict[str, list[str]]:
    if not enforcer:
         raise NotFoundException("Authorization service not available")

    # get_filtered_grouping_policy(0, id) returns list of [user, role]
    # This reads from memory, so it is synchronous
    grouping_policies = enforcer.get_filtered_grouping_policy(0, id)
    roles = [rule[1] for rule in grouping_policies if len(rule) > 1]

    return {"roles": roles}
