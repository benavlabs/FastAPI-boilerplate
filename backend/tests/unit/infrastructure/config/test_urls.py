"""URLs built from configuration have to survive the credentials people actually use."""

from configparser import ConfigParser

import pytest
from sqlalchemy.engine import make_url

from src.infrastructure.config.base import CoreSettings, ini_value
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


def test_the_database_name_may_not_hide_url_punctuation():
    """SQLAlchemy reads the name literally, so a '?' in it would silently split the URL."""
    settings = CoreSettings(POSTGRES_DB="my/db?x#y")

    with pytest.raises(ValueError, match="POSTGRES_DB"):
        settings.DATABASE_URL


def test_a_database_name_with_a_space_still_round_trips():
    settings = CoreSettings(POSTGRES_DB="my db")

    assert make_url(settings.DATABASE_URL).database == "my db"


def test_an_override_is_used_as_given():
    settings = CoreSettings(DATABASE_URL="postgresql+asyncpg://u:p@h:5432/any?thing")

    assert settings.DATABASE_URL == "postgresql+asyncpg://u:p@h:5432/any?thing"


def test_a_percent_in_the_url_survives_the_alembic_config():
    """Alembic reads its url through ConfigParser, where a bare '%' starts an interpolation."""
    url = CoreSettings(POSTGRES_PASSWORD=AWKWARD, POSTGRES_DB="app").DATABASE_URL
    parser = ConfigParser()
    parser.read_string(f"[alembic]\nsqlalchemy.url = {ini_value(url)}\n")

    assert parser.get("alembic", "sqlalchemy.url") == url
    assert make_url(parser.get("alembic", "sqlalchemy.url")).password == AWKWARD
