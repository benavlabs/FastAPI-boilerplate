"""The initial-data steps ``scripts/setup_initial_data.py`` runs, in order.

Hand-maintained until the generator exists.
"""

from collections.abc import Awaitable, Callable

from scripts.create_first_superuser import create_first_superuser
from scripts.create_first_tier import create_first_tier

SEEDERS: tuple[Callable[[], Awaitable[None]], ...] = (
    create_first_tier,
    create_first_superuser,
)
