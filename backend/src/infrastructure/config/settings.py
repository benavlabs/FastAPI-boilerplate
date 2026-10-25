"""Application settings.

The core mixins live in ``base``; each feature ships its own mixin next to its
code, and ``src/wiring/settings.py`` composes the ones this project selected into
``Settings``. Import settings from here: this facade is stable whatever features
are installed.
"""

from ...wiring.settings import Settings, settings
from .base import (
    APIDocSettings,
    APISettings,
    AppSettings,
    ClientCacheSettings,
    CompressionSettings,
    CoreSettings,
    CORSSettings,
    DatabaseSettings,
    EnvironmentOption,
    EnvironmentSettings,
    LoggingSettings,
    SecuritySettings,
    config,
)

__all__ = [
    "APIDocSettings",
    "APISettings",
    "AppSettings",
    "ClientCacheSettings",
    "CompressionSettings",
    "CORSSettings",
    "CoreSettings",
    "DatabaseSettings",
    "EnvironmentOption",
    "EnvironmentSettings",
    "LoggingSettings",
    "SecuritySettings",
    "Settings",
    "config",
    "get_settings",
    "settings",
]


def get_settings() -> Settings:
    """Return the application settings."""
    return settings
