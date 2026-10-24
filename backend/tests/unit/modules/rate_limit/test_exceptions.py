"""The rate-limit errors, and what they say to a client."""

from src.modules.common.utils.error_handler import map_exception
from src.modules.rate_limit.exceptions import RateLimitNotFoundError


def test_ratelimitnotfounderror_tells_the_client_what_is_missing():
    http_exc = map_exception(RateLimitNotFoundError("internal detail the client must not see"))

    assert http_exc.detail == "Rate limit configuration not found."
