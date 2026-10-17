"""The tier errors, and what they say to a client."""

from src.modules.common.utils.error_handler import map_exception
from src.modules.tier.exceptions import TierNotFoundError


def test_tiernotfounderror_tells_the_client_what_is_missing():
    http_exc = map_exception(TierNotFoundError("internal detail the client must not see"))

    assert http_exc.detail == "The requested tier was not found."
