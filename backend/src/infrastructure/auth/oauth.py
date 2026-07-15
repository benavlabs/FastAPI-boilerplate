"""crudauth OAuth building blocks for the boilerplate's own OAuth routes.

Runs the existing ``/oauth/google`` routes on crudauth's hardened OAuth
(PKCE + signed state + verified-email account linking) without mounting crudauth's
own oauth router - which would change the URLs. We construct the provider, a
per-request state store, and the account-linking service here and drive them from
the route handlers in ``routes.py``.
"""

from crudauth.oauth import GenericOIDCProvider, OAuthAccountService, OAuthProviderFactory
from crudauth.storage import get_session_storage

from ..config.settings import settings
from .setup import _session_redis_url, _use_redis, auth

OAUTH_STATE_TTL_SECONDS = 1800

_redirect_base = settings.OAUTH_REDIRECT_BASE_URL.rstrip("/")


def _build_provider(name: str, client_id: str, client_secret: str):
    return OAuthProviderFactory.create_provider(
        name,
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=f"{_redirect_base}/api/v1/auth/oauth/callback/{name}",
    )


# Add a provider here (and wire its routes in routes.py) to enable it.
oauth_providers = {
    "google": _build_provider("google", settings.OAUTH_GOOGLE_CLIENT_ID, settings.OAUTH_GOOGLE_CLIENT_SECRET),
}

# OIDC RP-initiated logout: provider name -> end_session endpoint. ``/logout``
# uses this to hand the client a ``logout_url`` that also terminates the IdP's
# own SSO session; the ``id_token`` needed as the hint is stashed in the session
# metadata at callback time. The post-logout target must be registered with the
# IdP as a "Post Logout URI".
oauth_end_session_endpoints: dict[str, str] = {}
oauth_post_logout_redirect_uri = f"{_redirect_base}/"

# Zitadel is a generic OIDC provider keyed on an issuer, which the factory's
# create_provider cannot pass, so it is constructed directly. The endpoints are
# Zitadel's standard layout under the issuer (confirm against
# {issuer}/.well-known/openid-configuration; GenericOIDCProvider.from_discovery
# resolves them dynamically instead, but is async and this module builds at
# import time). The secret is a mode switch, not a requirement: set ->
# confidential client (Zitadel app auth method POST); empty -> public client
# (auth method PKCE), where crudauth omits client auth from the token exchange.
if settings.OAUTH_ZITADEL_ISSUER and settings.OAUTH_ZITADEL_CLIENT_ID:
    _zitadel_issuer = settings.OAUTH_ZITADEL_ISSUER.rstrip("/")
    oauth_providers["zitadel"] = GenericOIDCProvider(
        settings.OAUTH_ZITADEL_CLIENT_ID,
        settings.OAUTH_ZITADEL_CLIENT_SECRET,
        f"{_redirect_base}/api/v1/auth/oauth/callback/zitadel",
        scopes=["openid", "profile", "email"],
        authorize_endpoint=f"{_zitadel_issuer}/oauth/v2/authorize",
        token_endpoint=f"{_zitadel_issuer}/oauth/v2/token",
        userinfo_endpoint=f"{_zitadel_issuer}/oidc/v1/userinfo",
        provider_name="zitadel",
        issuer=_zitadel_issuer,
    )
    oauth_end_session_endpoints["zitadel"] = f"{_zitadel_issuer}/oidc/v1/end_session"

oauth_state_storage = get_session_storage(
    "redis" if _use_redis else "memory",
    prefix="oauth_state:",
    expiration=OAUTH_STATE_TTL_SECONDS,
    redis_url=_session_redis_url if _use_redis else None,
)

oauth_account_service = OAuthAccountService(
    repo=auth.repo,
    # suggested_name is the provider's full name, unbounded; User.name is String(30).
    new_user_fields=lambda ctx: {"name": ctx.suggested_name[:30]},
)
