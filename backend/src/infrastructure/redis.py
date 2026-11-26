"""A factory for the Redis clients features own, and the URLs that name them."""

from urllib.parse import quote

from redis.asyncio import Redis


def make_redis_client(host: str, port: int, db: int, password: str | None, pool_size: int, timeout: int, *, ssl: bool) -> Redis:
    """A pooled async Redis client. Each feature builds its own and closes it in its lifecycle.

    ``ssl`` is the feature's own ``*_REDIS_SSL``, and has no default, so no caller connects in
    plaintext by leaving it out.
    """
    return Redis(
        host=host,
        port=port,
        db=db,
        password=password,
        socket_timeout=timeout,
        max_connections=pool_size,
        decode_responses=False,
        ssl=ssl,
    )


def redis_url(host: str, port: int, db: int, password: str | None, *, ssl: bool) -> str:
    """A Redis URL with the password escaped, so one containing ``@`` or ``/`` still parses, and the
    ``rediss`` scheme when the connection speaks TLS."""
    credentials = f":{quote(password, safe='')}@" if password else ""
    scheme = "rediss" if ssl else "redis"

    return f"{scheme}://{credentials}{host}:{port}/{db}"
