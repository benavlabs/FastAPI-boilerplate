"""The annotated dependencies routes use to ask for the caller.

They live with accounts because that is the feature that resolves a caller. Core
keeps the database session, which every project has.
"""

from typing import Annotated, Any

from crudauth import Principal
from fastapi import Depends
from fastapi.security import OAuth2PasswordRequestForm

from ...modules.common.schemas import NUL
from ..http_exceptions import UnprocessableEntityException
from .authorization import get_current_permissions
from .dependencies import (
    get_current_principal,
    get_current_superuser,
    get_current_user,
    get_freshly_signed_in_principal,
    get_optional_user,
    get_session_principal,
)

CurrentPrincipalDep = Annotated[Principal, Depends(get_current_principal)]

SessionPrincipalDep = Annotated[Principal, Depends(get_session_principal)]
"""The caller of a route reserved for a signed-in session; another credential answers 401."""

FreshSessionPrincipalDep = Annotated[Principal, Depends(get_freshly_signed_in_principal)]
"""The caller of a route that asks for a sign-in no older than ``FRESH_SIGN_IN_SECONDS``."""

CurrentPermissionsDep = Annotated[frozenset[str], Depends(get_current_permissions)]
"""The caller's effective permissions, resolved once per request."""

CurrentUserDep = Annotated[dict[str, Any], Depends(get_current_user)]
CurrentSuperUserDep = Annotated[dict[str, Any], Depends(get_current_superuser)]
OptionalUserDep = Annotated[dict[str, Any] | None, Depends(get_optional_user)]


def credentials_a_database_can_hold(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
) -> OAuth2PasswordRequestForm:
    """The submitted credentials, refused where either field carries a NUL character.

    The identifier reaches a query that Postgres refuses outright, so a login carrying one
    answered 500 with a traceback, for a form anybody can post. No stored password can hold
    a NUL either, since the schemas refuse one at signup.

    Raises:
        UnprocessableEntityException: The username or the password holds a NUL character.
    """
    if NUL in form_data.username or NUL in form_data.password:
        raise UnprocessableEntityException(detail="Credentials cannot carry a NUL character.")

    return form_data


OAuth2FormDep = Annotated[OAuth2PasswordRequestForm, Depends(credentials_a_database_can_hold)]
