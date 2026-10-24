"""The decorator a route caches its response with.

Hand-maintained until the generator exists: imports and literals only.
"""

from ..infrastructure.cache.decorator import cache as cached

__all__ = ["cached"]
