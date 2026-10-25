"""Tier errors."""

from ..common.exceptions import ResourceNotFoundError


class TierNotFoundError(ResourceNotFoundError):
    """Raised when a tier cannot be found."""

    public_detail = "The requested tier was not found."
