"""The route a request matched, as the throttle and its resolvers name it."""

from fastapi import Request


def throttled_path(request: Request) -> str:
    """The matched route's declared path, falling back to the requested path."""
    route = request.scope.get("route")

    return getattr(route, "path", None) or request.url.path
