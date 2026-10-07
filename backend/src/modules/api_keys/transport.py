"""The ``X-API-Key`` transport: a request authenticated by a key, as the key's owner."""

from crudauth import AuthContext, Principal, Transport
from crudauth.exceptions import UnauthorizedException
from starlette.requests import Request

from .service import APIKeyService

API_KEY_HEADER = "X-API-Key"
TRANSPORT_NAME = "apikey"

INVALID_KEY = "Invalid API key"


class APIKeyTransport(Transport):
    """Authenticates a request by the key its ``X-API-Key`` header carries.

    A request without the header carries no credential here, so the facade moves on to
    the next transport. A header that carries anything else answers 401: a key that is
    unknown, revoked, expired, or whose owner a soft delete has taken out.
    """

    name = TRANSPORT_NAME

    def __init__(self, service: APIKeyService | None = None) -> None:
        self._service = service or APIKeyService()

    async def authenticate(self, request: Request, ctx: AuthContext) -> Principal | None:
        """The owner of the key the header carries, or ``None`` when it carries none."""
        presented = request.headers.get(API_KEY_HEADER)
        if not presented:
            return None

        validated = await self._service.validate_api_key(api_key=presented, db=ctx.db)
        owner = await ctx.resolve_user(validated.user_id) if validated.is_valid else None
        if owner is None or not ctx.repo.is_active(owner):
            raise UnauthorizedException(INVALID_KEY)

        return ctx.build_principal(
            user_id=ctx.repo.user_id(owner),
            user=owner,
            transport=self.name,
            metadata={"api_key_id": validated.api_key_id},
        )
