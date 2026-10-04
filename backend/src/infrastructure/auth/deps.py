"""The annotated dependencies routes use to ask for the caller.

They live with accounts because that is the feature that resolves a caller. Core
keeps the database session, which every project has.
"""

from typing import Annotated, Any

from crudauth import Principal
from fastapi import Depends
from fastapi.security import OAuth2PasswordRequestForm

from .authorization import get_current_permissions
from .dependencies import (
    get_current_principal,
    get_current_superuser,
    get_current_user,
    get_optional_user,
)

CurrentPrincipalDep = Annotated[Principal, Depends(get_current_principal)]

CurrentPermissionsDep = Annotated[frozenset[str], Depends(get_current_permissions)]
"""The caller's effective permissions, resolved once per request."""

CurrentUserDep = Annotated[dict[str, Any], Depends(get_current_user)]
CurrentSuperUserDep = Annotated[dict[str, Any], Depends(get_current_superuser)]
OptionalUserDep = Annotated[dict[str, Any] | None, Depends(get_optional_user)]

OAuth2FormDep = Annotated[OAuth2PasswordRequestForm, Depends()]
