import logging
from typing import Any

from starlette.authentication import (
    AuthCredentials,
    AuthenticationBackend,
    SimpleUser,
)
from starlette.requests import HTTPConnection

from ..core.authz.casbin import enforcer
from ..core.db.database import local_session
from ..core.security import TokenType, verify_token
from ..crud.crud_users import crud_users

logger = logging.getLogger(__name__)


class AuthenticatedUser(SimpleUser):
    def __init__(
        self,
        username: str,
        user_id: str,
        is_superuser: bool,
        tier_id: str | None = None,
        extra_data: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(username)
        self.id = user_id
        self.is_superuser = is_superuser
        self.tier_id = tier_id
        self.extra_data = extra_data or {}


class JWTAuthenticationBackend(AuthenticationBackend):
    async def authenticate(self, conn: HTTPConnection) -> tuple[AuthCredentials, AuthenticatedUser] | None:
        if "Authorization" not in conn.headers:
            try:
                if enforcer:
                    subject = "anonymous"
                    path = conn.url.path
                    method = conn.scope.get("method", "GET")
                    allowed = await enforcer.enforce(subject, path, method)
                    if allowed:
                        return AuthCredentials(["authenticated"]), AuthenticatedUser(
                            username=subject,
                            user_id=subject,
                            is_superuser=False,
                            tier_id=None,
                            extra_data={}
                        )
            except Exception as e:
                logger.error(f"Authentication error (anonymous check): {e}")
            return None

        auth = conn.headers["Authorization"]
        try:
            scheme, token = auth.split()
            if scheme.lower() != "bearer":
                return None
        except ValueError:
            return None

        try:
            async with local_session() as db:
                token_data = await verify_token(token, TokenType.ACCESS, db)
                if not token_data:
                    return None

                # Load user
                if "@" in token_data.username_or_email:
                    user = await crud_users.get(db=db, email=token_data.username_or_email, is_deleted=False)
                else:
                    user = await crud_users.get(db=db, username=token_data.username_or_email, is_deleted=False)

                if not user:
                    return None
                if enforcer and user["is_superuser"]:
                    try:
                        await enforcer.add_grouping_policy(str(user["id"]), "role:superuser")
                    except Exception as e:
                        logger.error(f"Failed to ensure superuser role mapping: {e}")

                return AuthCredentials(["authenticated"]), AuthenticatedUser(
                    username=str(user["id"]),
                    user_id=str(user["id"]),
                    is_superuser=user["is_superuser"],
                    tier_id=str(user["tier_id"]) if user["tier_id"] else None,
                    extra_data=dict(user)
                )
        except Exception as e:
            logger.error(f"Authentication error: {e}")
            return None
