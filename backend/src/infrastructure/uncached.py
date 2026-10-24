"""The response caching a project without the cache feature has: none.

The wiring picks between this and the cache feature's decorator, so a route asks for
caching without depending on whether the project kept the feature that provides it.
"""

from collections.abc import Callable
from typing import Any, TypeVar

T = TypeVar("T", bound=Callable[..., Any])


def cached(**options: Any) -> Callable[[T], T]:
    """Return the route as it is, whatever caching it asked for."""

    def wrapper(func: T) -> T:
        return func

    return wrapper
