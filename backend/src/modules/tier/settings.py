"""Settings for the tiers feature."""

from pydantic_settings import BaseSettings

from ...infrastructure.config.base import config


class TierSettings(BaseSettings):
    """The tier new users are given when none is named."""

    DEFAULT_TIER_NAME: str = config("DEFAULT_TIER_NAME", default="free")
