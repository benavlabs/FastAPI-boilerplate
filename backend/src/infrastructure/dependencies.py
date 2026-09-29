from typing import Annotated, Any

from crudauth import Principal
from fastapi import Depends
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession

from .auth.authorization import get_current_permissions
from .auth.dependencies import (
    get_current_principal,
    get_current_superuser,
    get_current_user,
    get_optional_user,
)
from .database.session import async_session

# Database
AsyncSessionDep = Annotated[AsyncSession, Depends(async_session)]

# Authentication
CurrentPrincipalDep = Annotated[Principal, Depends(get_current_principal)]

# Authorization (effective permissions, resolved once per request)
CurrentPermissionsDep = Annotated[frozenset[str], Depends(get_current_permissions)]

# Users (dict-compat, resolved by crudauth)
CurrentUserDep = Annotated[dict[str, Any], Depends(get_current_user)]
CurrentSuperUserDep = Annotated[dict[str, Any], Depends(get_current_superuser)]
OptionalUserDep = Annotated[dict[str, Any] | None, Depends(get_optional_user)]

# Auth form
OAuth2FormDep = Annotated[OAuth2PasswordRequestForm, Depends()]
