from typing import Annotated, Any

from fastapi import Depends
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession

from .auth.dependencies import get_current_superuser, get_current_user, get_optional_user
from .database.session import async_session

# Database
AsyncSessionDep = Annotated[AsyncSession, Depends(async_session)]

# Users (dict-compat, resolved by crudauth)
CurrentUserDep = Annotated[dict[str, Any], Depends(get_current_user)]
CurrentSuperUserDep = Annotated[dict[str, Any], Depends(get_current_superuser)]
OptionalUserDep = Annotated[dict[str, Any] | None, Depends(get_optional_user)]

# Auth form
OAuth2FormDep = Annotated[OAuth2PasswordRequestForm, Depends()]
