"""The account routes this project mounts, and the OAuth router it mounts outside the API prefix.

``router`` carries crudauth's account router under ``/auth``, with ``set-password`` left out,
and its recovery router: email verification, password reset and the confirmed email change.
``root_routers`` carries crudauth's OAuth router when a provider is configured, and is empty
when none is.

The routes in ``SESSION_ONLY_PATHS`` are mounted behind ``get_session_principal``: changing a
password, moving an address and ending a session are things an account does while signed in,
not things another credential does on its behalf.
"""

from typing import Annotated, Any, cast

from crudauth import Principal
from crudauth.account import build_account_router
from crudauth.email.router import build_email_router
from crudauth.exceptions import ForbiddenException, UnauthorizedException
from crudauth.ratelimit import KeyBy
from crudauth.utils import is_cross_site
from fastapi import APIRouter, Depends, Form, Query, Request, Response
from fastapi.routing import APIRoute

from ...modules.user.crud import crud_users
from ..dependencies import AsyncSessionDep
from ..logging import get_logger
from .dependencies import get_optional_principal, get_session_principal
from .deps import OAuth2FormDep
from .setup import auth as crud_auth
from .setup import session_transport

logger = get_logger()

router = APIRouter(tags=["Authentication"])

SESSION_ONLY_PATHS = ("/change-password", "/email/change-request")
"""The crudauth routes this project reserves for a signed-in session."""


def _mount(source: APIRouter) -> None:
    """Mount ``source``'s routes under ``router``, each with the gates its path calls for."""
    open_router, session_only = APIRouter(), APIRouter()
    for route in source.routes:
        api_route = cast(APIRoute, route)
        api_route.tags = []
        target = session_only if api_route.path in SESSION_ONLY_PATHS else open_router
        target.routes.append(api_route)

    router.include_router(open_router)
    router.include_router(session_only, dependencies=[Depends(get_session_principal)])


_account_router = build_account_router(crud_auth, crud_auth.sessions)
_account_router.routes = [
    route for route in _account_router.routes if isinstance(route, APIRoute) and route.path != "/set-password"
]
_mount(_account_router)

if crud_auth.emails is not None:
    _mount(build_email_router(auth=crud_auth, service=crud_auth.emails))

root_routers: tuple[APIRouter, ...] = (crud_auth.oauth_router,) if crud_auth.oauth is not None else ()


@router.post(
    "/login",
    summary="User Login",
    description="""
            Authenticates a user and creates a new session.

            This endpoint accepts username/email and password credentials and verifies them.
            On successful authentication:
            - A new session is created
            - A session ID is set as an HTTP-only cookie
            - A CSRF token is generated for protection against CSRF attacks

            With remember_me=true the session cookie persists across browser
            restarts; otherwise it ends with the browser session.

            The endpoint is protected by rate limiting to prevent brute force attacks.
            After multiple failed attempts, further login attempts will be temporarily blocked.
            A request the browser marks as sent from another site is refused, so a
            third-party page can't sign a visitor into an account it controls.
            """,
    responses={
        200: {"description": "Login successful, session created"},
        401: {"description": "Authentication failed"},
        403: {"description": "Cross-site login request"},
        429: {"description": "Too many login attempts, try again later"},
    },
    response_description="The signed-in user's id and username, and the CSRF token for subsequent requests",
)
async def login(
    request: Request,
    response: Response,
    form_data: OAuth2FormDep,
    db: AsyncSessionDep,
    remember_me: Annotated[bool, Form()] = False,
) -> dict[str, Any]:
    """Login endpoint to get session cookies.

    Credentials go through crudauth's ``authenticate_password`` (timing-equalized
    check, disabled-account guard, escalating lockout that answers 429 +
    Retry-After), and the session is completed by the session transport, which
    sets the cookies and fires the ``on_after_login`` hook.
    """
    if is_cross_site(request):
        raise ForbiddenException("Cross-site login requests are not allowed.")

    user = await crud_auth.authenticate_password(db, form_data.username, form_data.password, request=request)
    return await session_transport.complete_login(
        request,
        response,
        user,
        {
            "remember_me": remember_me,
            "metadata": {"login_type": "password", "username": crud_auth.repo.get(user, "username")},
        },
    )


@router.post(
    "/logout",
    summary="User Logout",
    description="""
            Terminates the current user session.

            This endpoint:
            - Invalidates the active session in the storage backend
            - Clears the cookies of every configured transport

            After logout, the user will need to authenticate again to access
            protected resources. Any existing session tokens will no longer be valid.
            """,
    responses={200: {"description": "Logout successful, session terminated"}, 401: {"description": "Not authenticated"}},
    response_description="Confirmation of successful logout",
)
async def logout(
    request: Request,
    response: Response,
    db: AsyncSessionDep,
    _: Annotated[Principal, Depends(get_session_principal)],
) -> dict[str, str]:
    """End the session the cookie names, clear the cookies and run the logout hook.

    The session transport does all of it (CSRF-protected); the dependency is what
    reserves the route for a session.
    """
    await session_transport.complete_logout(request, response, db)

    return {"message": "Logged out successfully"}


@router.post(
    "/logout-all",
    summary="Logout All Sessions",
    description="""
            Terminates every active session for the current user, across all devices.

            Use this to "log out everywhere" after a suspected compromise. By default it
            invalidates every session the user holds, including the one making the
            request, and clears the current client's cookies.

            Pass keep_current=true to keep the calling session and sign out only the
            other devices.
            """,
    responses={
        200: {"description": "Sessions terminated"},
        401: {"description": "Not authenticated"},
        429: {"description": "Too many requests, try again later"},
    },
    response_description="Confirmation with the number of sessions terminated",
    dependencies=[Depends(crud_auth.rate_limit("logout_all", key=KeyBy.USER))],
)
async def logout_all(
    response: Response,
    principal: Annotated[Principal, Depends(get_session_principal)],
    keep_current: bool = Query(False, description="Keep the calling session and sign out every other device"),
) -> dict[str, Any]:
    """Terminate the current user's sessions (CSRF-protected); ``keep_current`` spares the calling one."""
    spared_session_id = principal.metadata.get("session_id") if keep_current else None
    terminated = await crud_auth.sessions.revoke_all(principal.user_id, exclude=spared_session_id)
    if spared_session_id:
        return {"message": "All other sessions terminated.", "terminated_count": terminated}

    crud_auth.sessions.clear_session_cookies(response)

    return {"message": "All sessions terminated. Please log in again.", "terminated_count": terminated}


@router.post(
    "/refresh-csrf",
    summary="Refresh CSRF Token",
    description="""
            Generates a new CSRF token for the current session.

            This endpoint should be called to obtain a fresh CSRF token when:
            - The current token is about to expire
            - After a certain period of inactivity
            - When increased security is needed for sensitive operations

            The new token is returned in the response and also set as a cookie.
            """,
    responses={200: {"description": "New CSRF token generated successfully"}, 401: {"description": "Not authenticated"}},
    response_description="The new CSRF token for the session",
)
async def refresh_csrf_token(
    request: Request,
    response: Response,
) -> dict[str, str]:
    """Generate a new CSRF token for the current session.

    Deliberately resolves the session cookie directly rather than via
    ``current_user`` - requiring a valid CSRF header to refresh CSRF would defeat
    the recovery purpose. The session cookie is httpOnly and the new token only
    lands in the (same-origin-readable) cookie + body.
    """
    sessions = crud_auth.sessions
    session_id = request.cookies.get(sessions.session_cookie_name)
    session = await sessions.validate_session(session_id) if session_id else None
    if session is None or session_id is None:
        raise UnauthorizedException("Not authenticated")

    ttl_seconds = sessions.timeout_seconds_for(session.metadata)
    csrf_token = await sessions.regenerate_csrf_token(session_id, expiration_seconds=ttl_seconds)
    sessions.set_csrf_cookie(response, csrf_token, max_age=ttl_seconds)

    return {"csrf_token": csrf_token}


@router.get("/check-auth")
async def check_auth(
    principal: Annotated[Principal | None, Depends(get_optional_principal)],
    db: AsyncSessionDep,
) -> dict[str, Any]:
    """
    Check if the user is authenticated and return basic user information.

    This is useful for clients to verify authentication status. It responds to both
    authenticated and anonymous callers (anonymous gets ``authenticated: false``
    rather than a 401).

    Returns:
        Authentication status and user information if authenticated.
    """
    if principal is None:
        return {"authenticated": False, "message": "Not authenticated"}

    try:
        user = await crud_users.get(db=db, id=principal.user_id, is_deleted=False)

        if not user:
            return {"authenticated": False, "message": "User not found"}

        session_id = principal.metadata.get("session_id")
        session = await crud_auth.sessions.validate_session(session_id) if session_id else None

        return {
            "authenticated": True,
            "user": {
                "id": user["id"],
                "username": user["username"],
                "email": user["email"],
                "oauth_provider": user.get("oauth_provider"),
            },
            "session": {
                "created_at": session.created_at.isoformat() if session and session.created_at else None,
                "last_activity": session.last_activity.isoformat() if session and session.last_activity else None,
            },
        }
    except Exception as e:
        logger.error(f"Error checking authentication: {str(e)}", exc_info=True)
        return {"authenticated": False, "message": "Error checking authentication status"}
