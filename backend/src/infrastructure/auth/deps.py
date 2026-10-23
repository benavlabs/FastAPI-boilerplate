"""The annotated dependencies routes use to ask for the caller.

They live with accounts because that is the feature that resolves a caller. Core
keeps the database session, which every project has.
"""

import json
from email.message import Message
from typing import Annotated, Any

from crudauth import Principal
from fastapi import Depends, Request
from fastapi.security import OAuth2PasswordRequestForm

from ...modules.common.schemas import NUL, refuse_unencodable_text
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


JSON_SUBTYPE = "json"
JSON_SUFFIX = "+json"
"""An ``application`` subtype FastAPI parses as JSON, which is what carries the escapes."""

THE_BODY = "the body"
"""What a refusal names when the text is a key rather than a field's value."""

NOTHING = object()
"""What a body the route parses as nothing reads as, which ``None`` is a parsed body of."""

REDIRECT_FIELD = "redirect_to"
"""The field a recovery request carries the destination in, which crudauth signs into its token."""

REDIRECT_MAX_LENGTH = 2048
"""How long that destination may be, the length a URL is held to everywhere else."""


async def a_redirect_a_link_can_carry(request: Request) -> None:
    """Refuse a request asking to be sent somewhere no link could hold.

    crudauth takes ``redirect_to`` as a plain ``str`` and keeps it until the person comes
    back: a recovery request has it signed into the token the emailed link carries, so a
    megabyte of path is a megabyte of link in somebody's mailbox and a token of the same
    size on the way back, and an OAuth sign-in has it stored with the flow's state until
    the callback. The one arrives in the body and the other in the query, so both are
    read here. The destination is dropped rather than refused where it is not a
    same-origin path, which crudauth does, so the length is all this answers for.

    Raises:
        UnprocessableEntityException: The destination is longer than ``REDIRECT_MAX_LENGTH``.
    """
    _refuse_a_destination_too_long(request.query_params.get(REDIRECT_FIELD))

    payload = await _json_payload(request)
    if isinstance(payload, dict):
        _refuse_a_destination_too_long(payload.get(REDIRECT_FIELD))


def _refuse_a_destination_too_long(asked: Any) -> None:
    """Answer ``422`` where ``asked`` is a destination longer than a link can hold.

    Raises:
        UnprocessableEntityException: ``asked`` is text longer than ``REDIRECT_MAX_LENGTH``.
    """
    if isinstance(asked, str) and len(asked) > REDIRECT_MAX_LENGTH:
        raise UnprocessableEntityException(detail=f"{REDIRECT_FIELD} cannot be longer than {REDIRECT_MAX_LENGTH} characters.")


async def body_a_database_can_hold(request: Request) -> None:
    """Refuse a JSON body holding text no column can store.

    crudauth owns these bodies and takes their fields as plain ``str``. A lone surrogate
    reaches them only through a JSON escape, since percent-decoding replaces one: in a
    token it reaches ``jwt.decode``, which encodes the token as UTF-8 and raises, so the
    three confirm routes answered 500 to anybody, and in a new password it reaches the
    hash. A NUL is refused here as well, as this project's schemas and its login form do.
    This project's own bodies carry ``EncodableText`` instead.

    A body that is not JSON, is empty, or does not parse is left to the route, which
    answers for it.

    Raises:
        UnprocessableEntityException: A field holds text no column can store.
    """
    payload = await _json_payload(request)
    if payload is NOTHING:
        return

    if not isinstance(payload, dict):
        _refuse_unstorable_text(THE_BODY, payload)
        return

    _refuse_unstorable_text(THE_BODY, list(payload))
    for name, value in payload.items():
        _refuse_unstorable_text(str(name), value)


async def _json_payload(request: Request) -> Any:
    """What the route will parse this body as, or ``NOTHING`` where it parses nothing.

    A body that is not JSON, is empty, or does not parse is left to the route, which
    answers for it.
    """
    if not _reaches_the_route_as_json(request):
        return NOTHING

    body = await request.body()
    if not body:
        return NOTHING

    try:
        return json.loads(body)
    except ValueError:
        return NOTHING


def _reaches_the_route_as_json(request: Request) -> bool:
    """Whether FastAPI will parse this body as JSON, read the way ``fastapi.routing`` reads it.

    An ``application`` type whose subtype is ``json`` or ends in ``+json``, so
    ``application/merge-patch+json`` counts and a charset parameter does not get in the way.
    A body with no content type is not parsed as JSON at all while routes keep
    ``strict_content_type``, so it never reaches a field as text.
    """
    content_type = request.headers.get("content-type")
    if not content_type:
        return False

    header = Message()
    header["content-type"] = content_type
    subtype = header.get_content_subtype()

    return header.get_content_maintype() == "application" and (subtype == JSON_SUBTYPE or subtype.endswith(JSON_SUFFIX))


def _refuse_unstorable_text(name: str, value: Any) -> None:
    """Answer ``422`` for ``name`` when ``value`` holds text no column can store.

    Raises:
        UnprocessableEntityException: Something inside ``value`` is a lone surrogate or a NUL.
    """
    try:
        refuse_unencodable_text(name, value)
    except ValueError as error:
        raise UnprocessableEntityException(detail=f"{name} cannot carry text the database cannot store.") from error


OAuth2FormDep = Annotated[OAuth2PasswordRequestForm, Depends(credentials_a_database_can_hold)]
