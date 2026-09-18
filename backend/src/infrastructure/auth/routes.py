from typing import Annotated, Any

from crudauth import Principal
from crudauth.exceptions import UnauthorizedException
from crudauth.ratelimit import KeyBy
from fastapi import APIRouter, Depends, Query, Request, Response

from ...modules.user.crud import crud_users
from ..dependencies import AsyncSessionDep, OAuth2FormDep
from ..logging import get_logger
from .dependencies import get_current_principal, get_optional_principal
from .setup import auth as crud_auth

logger = get_logger()

router = APIRouter(tags=["Authentication"])


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

            The endpoint is protected by rate limiting to prevent brute force attacks.
            After multiple failed attempts, further login attempts will be temporarily blocked.
            """,
    responses={
        200: {"description": "Login successful, session created"},
        401: {"description": "Authentication failed"},
        429: {"description": "Too many login attempts, try again later"},
    },
    response_description="CSRF token for use in subsequent requests",
)
async def login(
    request: Request,
    response: Response,
    form_data: OAuth2FormDep,
    db: AsyncSessionDep,
) -> dict[str, str]:
    """Login endpoint to get session cookies.

    The session ID is set as an HTTP-only cookie. The CSRF token is set as a
    regular cookie and returned in the response. Credentials are verified by
    crudauth's hardened ``authenticate_password`` (timing-equalized check,
    disabled-account guard, escalating lockout that returns 429 + Retry-After).
    """
    user = await crud_auth.authenticate_password(db, form_data.username, form_data.password, request=request)

    session_id, csrf_token = await crud_auth.sessions.create_session(
        request,
        user_id=crud_auth.repo.user_id(user),
        metadata={"login_type": "password", "username": crud_auth.repo.get(user, "username")},
    )
    crud_auth.sessions.set_session_cookies(response, session_id, csrf_token)

    return {"csrf_token": csrf_token}


@router.post(
    "/logout",
    summary="User Logout",
    description="""
            Terminates the current user session.

            This endpoint:
            - Invalidates the active session in the storage backend
            - Clears all session-related cookies from the client

            After logout, the user will need to authenticate again to access
            protected resources. Any existing session tokens will no longer be valid.
            """,
    responses={200: {"description": "Logout successful, session terminated"}, 401: {"description": "Not authenticated"}},
    response_description="Confirmation of successful logout",
)
async def logout(
    response: Response,
    principal: Annotated[Principal, Depends(get_current_principal)],
) -> dict[str, str]:
    """Logout endpoint to terminate the session and clear cookies (CSRF-protected)."""
    session_id = principal.metadata.get("session_id")
    if session_id:
        await crud_auth.sessions.revoke(session_id, owner_id=principal.user_id)
    crud_auth.sessions.clear_session_cookies(response)

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
    principal: Annotated[Principal, Depends(get_current_principal)],
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


if crud_auth.oauth is not None:
    router.include_router(crud_auth.oauth_router)


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
