from typing import Annotated

from fastapi import Depends

from .service import RoleService


def get_role_service() -> RoleService:
    return RoleService()


RoleServiceDep = Annotated[RoleService, Depends(get_role_service)]
