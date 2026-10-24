"""Settings for the API keys feature."""

from pydantic import Field
from pydantic_settings import BaseSettings

from ...infrastructure.config.base import config


class APIKeySettings(BaseSettings):
    """How long the usage rows a key's requests write are kept.

    A day count below zero is refused as the settings load, where a typo would otherwise
    read as the 0 that keeps every row.
    """

    KEY_USAGE_RETENTION_DAYS: int = Field(
        default=config("KEY_USAGE_RETENTION_DAYS", default=90, cast=int), ge=0, validate_default=True
    )
