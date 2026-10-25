"""Rate-limit configuration errors."""

from ..common.exceptions import ResourceNotFoundError


class RateLimitNotFoundError(ResourceNotFoundError):
    """Raised when a rate limit cannot be found."""

    public_detail = "Rate limit configuration not found."
