"""The initial-data steps ``scripts/setup_initial_data.py`` runs, in order.

Hand-maintained until the generator exists.
"""

from scripts.create_first_superuser import create_first_superuser
from scripts.create_first_tier import create_first_tier

SEEDERS = (
    create_first_tier,
    create_first_superuser,
)
