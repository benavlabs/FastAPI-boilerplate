"""Settings for the SQLAdmin panel."""

from pydantic_settings import BaseSettings

from ...infrastructure.config.base import config


class SQLAdminSettings(BaseSettings):
    """SQLAdmin interface settings."""

    ADMIN_ENABLED: bool = config("ADMIN_ENABLED", default=True, cast=bool)
    ADMIN_BASE_URL: str = config("ADMIN_BASE_URL", default="/admin")
