"""The crudauth helper the email-change guard counts through."""

import inspect

from crudauth.ratelimit import dependency

from src.infrastructure.auth.password_attempts import PASSWORD_ATTEMPT_ACTION, count_password_attempt
from src.infrastructure.auth.setup import auth as crud_auth


def test_the_helper_is_where_this_app_imports_it_from():
    assert "enforce_rate_limit" in dependency.__all__


def test_the_helper_takes_the_arguments_this_app_passes():
    parameters = inspect.signature(dependency.enforce_rate_limit).parameters

    assert list(parameters) == ["backend", "request", "response", "action", "identity", "limit", "principal"]
    for name in ("action", "identity", "limit"):
        assert parameters[name].kind is inspect.Parameter.KEYWORD_ONLY


def test_the_action_counted_is_the_one_change_password_uses():
    assert PASSWORD_ATTEMPT_ACTION in crud_auth.rate_limits
    assert crud_auth.rate_limits[PASSWORD_ATTEMPT_ACTION].times == 5


def test_counting_takes_the_request_and_the_user_it_charges():
    assert list(inspect.signature(count_password_attempt).parameters) == ["request", "user_id"]
