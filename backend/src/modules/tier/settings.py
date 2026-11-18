"""Settings for the tiers feature."""

from ...infrastructure.config.base import EnvSettings


class TierSettings(EnvSettings):
    """The tier new users are given when none is named."""

    DEFAULT_TIER_NAME: str = "free"
