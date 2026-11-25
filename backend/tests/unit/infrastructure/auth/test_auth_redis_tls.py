"""The sessions' and the rate limiter's Redis speak TLS when their settings say so."""

import pytest

from src.infrastructure.auth.settings import AuthSettings
from tests.fixtures.redis_tls import connection_in_a_fresh_process, spoken


def test_the_sessions_follow_the_cache_redis_tls_unless_they_say_otherwise():
    """The session connection falls back to the cache's, field by field, TLS among them."""
    assert AuthSettings(CACHE_REDIS_SSL=True).SESSION_REDIS_URL.startswith("rediss://")
    assert AuthSettings(CACHE_REDIS_SSL=True, SESSION_REDIS_SSL=False).SESSION_REDIS_URL.startswith("redis://")
    assert AuthSettings(SESSION_REDIS_SSL=True).SESSION_REDIS_URL.startswith("rediss://")
    assert AuthSettings().SESSION_REDIS_URL.startswith("redis://")


@pytest.mark.parametrize("ssl", [True, False])
def test_the_limiter_client_and_its_reported_target_speak_tls_when_the_setting_says(ssl: bool):
    shown = connection_in_a_fresh_process(
        {"RATE_LIMITER_BACKEND": "redis", "RATE_LIMITER_REDIS_SSL": str(ssl).lower()},
        "from src.infrastructure.auth.limiter import rate_limiter_redis_client as client; "
        "from src.infrastructure.auth.health import limiter_target as target",
        "client.connection_pool.connection_class.__name__, target().split(':')[0]",
    )

    assert shown == spoken(ssl)
