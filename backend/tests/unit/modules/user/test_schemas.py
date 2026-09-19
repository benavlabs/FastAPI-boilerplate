"""Unit tests for the User schemas."""

from src.infrastructure.auth.password_policy import password_policy
from src.infrastructure.auth.setup import auth
from src.infrastructure.config.settings import settings
from src.modules.user import schemas as user_schemas
from src.modules.user.schemas import UserCreate


def test_the_password_field_documents_the_configured_policy():
    """OpenAPI describes the policy crudauth enforces, from the same object."""
    field = UserCreate.model_json_schema()["properties"]["password"]

    assert field["minLength"] == settings.PASSWORD_MIN_LENGTH
    assert f"At least {settings.PASSWORD_MIN_LENGTH} characters" in field["description"]


def test_the_schema_leaves_enforcement_to_the_policy():
    """A weak password parses, so it's rejected by crudauth and never echoed in a validation error."""
    user = UserCreate(name="Test User", username="testuser", email="user.userson@example.com", password="weak")

    assert user.password == "weak"


def test_the_request_schema_and_crudauth_share_one_password_policy():
    """A second policy instance could document or accept rules crudauth doesn't enforce."""
    assert user_schemas.password_policy is password_policy
    assert auth.password_policy is password_policy


def test_the_password_policy_is_built_from_the_password_settings():
    assert password_policy.min_length == settings.PASSWORD_MIN_LENGTH
    assert password_policy.require_uppercase == settings.PASSWORD_REQUIRE_UPPERCASE
    assert password_policy.require_lowercase == settings.PASSWORD_REQUIRE_LOWERCASE
    assert password_policy.require_digit == settings.PASSWORD_REQUIRE_DIGIT
    assert password_policy.require_special == settings.PASSWORD_REQUIRE_SPECIAL


def test_the_password_field_is_driven_by_the_policy():
    field = UserCreate.model_json_schema()["properties"]["password"]

    assert field["minLength"] == password_policy.min_length
    assert field["description"] == password_policy.description
