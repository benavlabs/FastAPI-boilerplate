"""The signup route says where other features set what they add to a new account."""

from src.interfaces.main import app
from src.wiring import signup


def test_the_signup_route_names_the_wiring_a_new_account_takes_other_features_columns_from():
    description = app.openapi()["paths"]["/api/v1/users/"]["post"]["description"]

    assert signup.__file__.endswith("src/wiring/signup.py")
    assert "`src/wiring/signup.py`" in description
    assert "tier" not in description.lower()
