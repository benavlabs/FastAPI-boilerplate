"""The user errors, and what they say to a client."""

from src.modules.common.utils.error_handler import map_exception
from src.modules.user.exceptions import UserExistsError, UserNotFoundError


def test_usernotfounderror_tells_the_client_what_is_missing():
    http_exc = map_exception(UserNotFoundError("internal detail the client must not see"))

    assert http_exc.detail == "User not found."


def test_userexistserror_tells_the_client_what_is_missing():
    http_exc = map_exception(UserExistsError("internal detail the client must not see"))

    assert http_exc.detail == "A user with this email or username already exists."
