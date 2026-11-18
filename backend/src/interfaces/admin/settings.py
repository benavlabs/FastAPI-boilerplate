"""Settings for the SQLAdmin panel."""

from ...infrastructure.config.base import EnvSettings


class SQLAdminSettings(EnvSettings):
    """SQLAdmin interface settings."""

    ADMIN_ENABLED: bool = False
    ADMIN_BASE_URL: str = "/admin"
