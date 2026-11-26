"""Every Redis the project talks to speaks TLS when its own ``*_REDIS_SSL`` setting says so, and the
two things every feature builds its connection with carry that through."""

import pytest
from redis.asyncio.connection import Connection, SSLConnection

from src.infrastructure.redis import make_redis_client, redis_url


@pytest.mark.parametrize(("ssl", "scheme"), [(True, "rediss"), (False, "redis")])
def test_a_redis_url_names_the_scheme_its_connection_speaks(ssl: bool, scheme: str):
    assert redis_url("cache", 6379, 1, None, ssl=ssl) == f"{scheme}://cache:6379/1"


@pytest.mark.parametrize(("ssl", "connection"), [(True, SSLConnection), (False, Connection)])
def test_a_client_speaks_tls_when_asked(ssl: bool, connection: type):
    client = make_redis_client("cache", 6379, 0, None, 10, 5, ssl=ssl)

    assert client.connection_pool.connection_class is connection
