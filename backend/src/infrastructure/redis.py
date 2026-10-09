"""A factory for the Redis clients features own, and the URLs that name them."""

from urllib.parse import quote

from redis.asyncio import Redis


def make_redis_client(host: str, port: int, db: int, password: str | None, pool_size: int, timeout: int) -> Redis:
    """A pooled async Redis client. Each feature builds its own and closes it in its lifecycle."""
    return Redis(
        host=host,
        port=port,
        db=db,
        password=password,
        socket_timeout=timeout,
        max_connections=pool_size,
        decode_responses=False,
    )


def redis_url(host: str, port: int, db: int, password: str | None) -> str:
    """A Redis URL with the password escaped, so one containing ``@`` or ``/`` still parses."""
    credentials = f":{quote(password, safe='')}@" if password else ""

    return f"redis://{credentials}{host}:{port}/{db}"
