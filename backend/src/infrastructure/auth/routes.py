from typing import Annotated, Any

from crudauth import Principal
from crudauth.exceptions import UnauthorizedException
from crudauth.oauth import OAuthState
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import RedirectResponse

from ...modules.user.crud import crud_users
from ...modules.user.enums import OAuthProvider
from ..dependencies import AsyncSessionDep, OAuth2FormDep
from ..logging import get_logger
from .dependencies import get_current_principal, get_optional_principal
from .oauth import OAUTH_STATE_TTL_SECONDS, oauth_account_service, oauth_providers, oauth_state_storage
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
    csrf_token = await sessions.regenerate_csrf_token(
        user_id=session.user_id, session_id=session_id, expiration_seconds=ttl_seconds
    )
    sessions.set_csrf_cookie(response, csrf_token, max_age=ttl_seconds)

    return {"csrf_token": csrf_token}


@router.get(
    "/oauth/google",
    summary="Initiate Google OAuth Login",
    description="""
            Starts the OAuth 2.0 authentication flow with Google.

            This endpoint generates the authorization URL that the user should be
            redirected to in order to authenticate with Google. The flow includes:
            - Creation of a state parameter for CSRF protection
            - Generation of PKCE code challenge (for enhanced security)
            - Setting appropriate OAuth scopes for profile access

            After successful authentication with Google, the user will be redirected
            back to this application's callback endpoint.

            An optional redirect_uri can be specified to control where the user
            is sent after the entire authentication process completes.
            """,
    responses={
        200: {"description": "Authorization URL generated successfully"},
        500: {"description": "Failed to initiate Google login"},
    },
    response_description="The Google authorization URL to redirect the user to",
)
async def oauth_google_login(
    request: Request,
    redirect_uri: str | None = Query(None),
) -> dict[str, str]:
    """Initiate the Google OAuth flow: build the authorization URL and stash state + PKCE."""
    try:
        auth_data = oauth_providers["google"].get_authorization_url()
        state_obj = OAuthState(
            state=auth_data["state"],
            provider=OAuthProvider.GOOGLE.value,
            redirect_to=redirect_uri,
            code_verifier=auth_data.get("code_verifier"),
        )
        await oauth_state_storage.create(state_obj, session_id=auth_data["state"], expiration=OAUTH_STATE_TTL_SECONDS)
        return {"url": auth_data["url"]}
    except Exception as e:
        logger.error(f"Error initiating Google OAuth: {str(e)}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to initiate Google login")


@router.get(
    "/oauth/callback/google",
    summary="Google OAuth Callback Handler",
    description="""
            Processes the authentication callback from Google OAuth.

            This endpoint handles the authorization code returned by Google after
            the user has successfully authenticated. The process includes:
            - Validating the state parameter to prevent CSRF attacks
            - Exchanging the authorization code for access/refresh tokens
            - Fetching the user profile from Google
            - Creating or updating the user account in the system
            - Establishing a new session for the authenticated user

            Two response formats are supported:
            - redirect: Redirects to the frontend with success/error parameters (default)
            - json: Returns user information and tokens as a JSON response

            The json format is useful for mobile apps or single-page applications that
            handle the OAuth flow programmatically.
            """,
    responses={
        200: {"description": "Authentication successful (JSON response)"},
        302: {"description": "Authentication successful (redirect response)"},
        400: {"description": "Invalid OAuth state or other parameter"},
        401: {"description": "Authentication failed"},
        500: {"description": "Server error during authentication"},
    },
    response_description="Authentication result with session cookies set",
)
async def oauth_google_callback(
    request: Request,
    response: Response,
    db: AsyncSessionDep,
    code: str = Query(...),
    state: str = Query(...),
    response_format: str = Query("redirect", description="Response format, either 'redirect' or 'json'"),
):
    """Handle the Google OAuth callback: verify state, link/create the user, start a session."""
    state_data = await oauth_state_storage.get(state, OAuthState)

    if not state_data:
        logger.warning(f"Invalid OAuth state in callback: {state}")
        if response_format == "json":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid OAuth state")
        return RedirectResponse(
            url=f"/login?error=oauth_error&provider={OAuthProvider.GOOGLE.value}&reason=invalid_state",
            status_code=status.HTTP_302_FOUND,
        )

    if state_data.provider != OAuthProvider.GOOGLE.value:
        logger.warning(f"Provider mismatch in OAuth callback: expected google, got {state_data.provider}")
        if response_format == "json":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Provider mismatch")
        return RedirectResponse(
            url=f"/login?error=oauth_error&provider={OAuthProvider.GOOGLE.value}&reason=provider_mismatch",
            status_code=status.HTTP_302_FOUND,
        )

    try:
        provider = oauth_providers["google"]
        token_data = await provider.exchange_code(code, code_verifier=state_data.code_verifier)
        user_info_raw = await provider.get_user_info(token_data["access_token"])
        user_info = await provider.process_user_info(user_info_raw)

        user, is_new_user = await oauth_account_service.get_or_create_user(user_info, db)
        user_id = crud_auth.repo.user_id(user)
        username = crud_auth.repo.get(user, "username")

        session_id, csrf_token = await crud_auth.sessions.create_session(
            request,
            user_id=user_id,
            metadata={
                "login_type": "oauth",
                "oauth_provider": OAuthProvider.GOOGLE.value,
                "username": username,
                "is_new_user": is_new_user,
            },
        )
        crud_auth.sessions.set_session_cookies(response, session_id, csrf_token)

        await oauth_state_storage.delete(state)

        if response_format == "json":
            return {
                "success": True,
                "user": {
                    "id": user_id,
                    "username": username,
                    "email": crud_auth.repo.get(user, "email"),
                    "is_new_user": is_new_user,
                },
                "csrf_token": csrf_token,
            }

        redirect_to = str(state_data.redirect_to) if state_data.redirect_to else "/"
        return RedirectResponse(url=redirect_to, status_code=status.HTTP_302_FOUND)

    except Exception as e:
        logger.error(f"Error in Google OAuth callback: {str(e)}", exc_info=True)

        if response_format == "json":
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"OAuth authentication failed: {str(e)}"
            )

        return RedirectResponse(
            url=f"/login?error=oauth_error&provider={OAuthProvider.GOOGLE.value}",
            status_code=status.HTTP_302_FOUND,
        )


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
