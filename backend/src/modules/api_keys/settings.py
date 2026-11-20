"""Settings for the API keys feature."""

from pydantic import Field

from ...infrastructure.config.base import EnvSettings


class APIKeySettings(EnvSettings):
    """How long the usage rows a key's requests write are kept.

    A day count below zero is refused as the settings load, where a typo would otherwise
    read as the 0 that keeps every row.
    """

    KEY_USAGE_RETENTION_DAYS: int = Field(default=90, ge=0, validate_default=True)
