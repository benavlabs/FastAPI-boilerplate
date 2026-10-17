"""Caching: a ``@cache`` decorator and a provider API over Redis or Memcached.

Kept import-free apart from the installed-backend flags, like the rest of the
settings import path. Import from the submodules: ``.decorator``, ``.provider``,
``.backends``, ``.settings``.
"""

from importlib.util import find_spec

MEMCACHED_INSTALLED = find_spec("aiomcache") is not None
REDIS_INSTALLED = find_spec("redis.asyncio") is not None

__all__ = [
    "MEMCACHED_INSTALLED",
    "REDIS_INSTALLED",
]
