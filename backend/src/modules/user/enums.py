"""User enums for OAuth provider management."""

from enum import StrEnum


class OAuthProvider(StrEnum):
    """OAuth provider types for user authentication.

    These values are used to identify the OAuth provider used for registration
    and login. The string values must match the provider names used in the
    OAuth configuration and factory registration.
    """

    GOOGLE = "google"
    GITHUB = "github"
    ZITADEL = "zitadel"
