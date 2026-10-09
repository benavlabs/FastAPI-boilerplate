"""The project's settings: each selected feature's mixin on top of the core.

Hand-maintained until the generator exists. Core comes last, so a feature can
override a core default rather than the other way round.
"""

from ..infrastructure.auth.settings import AccountsSettings
from ..infrastructure.cache.settings import CacheSettings
from ..infrastructure.config.base import CoreSettings
from ..infrastructure.ratelimit.settings import RateLimitSettings
from ..infrastructure.taskiq.settings import TaskiqSettings
from ..interfaces.admin.settings import SQLAdminSettings
from ..modules.tier.settings import TierSettings


class Settings(
    AccountsSettings,
    RateLimitSettings,
    TierSettings,
    SQLAdminSettings,
    CacheSettings,
    TaskiqSettings,
    CoreSettings,
):
    """The settings of every selected feature, on top of the core."""


settings = Settings()
