"""URLs built from configuration have to survive the credentials people actually use."""

from sqlalchemy.engine import make_url

from src.infrastructure.config.base import CoreSettings
from src.infrastructure.redis import redis_url

AWKWARD = "p@ss/word#1:x%"


def test_the_database_password_survives_the_url():
    settings = CoreSettings(POSTGRES_PASSWORD=AWKWARD, POSTGRES_USER="app", POSTGRES_SERVER="db", POSTGRES_DB="app")

    assert make_url(settings.DATABASE_URL).password == AWKWARD


def test_the_redis_password_survives_the_url():
    url = redis_url("cache", 6379, 1, AWKWARD)

    assert make_url(url).password == AWKWARD


def test_a_redis_url_without_a_password_stays_plain():
    assert redis_url("cache", 6379, 1, None) == "redis://cache:6379/1"
