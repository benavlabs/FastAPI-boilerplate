"""Unit tests for the User schemas."""

from src.infrastructure.auth.password_policy import password_policy
from src.infrastructure.auth.setup import auth
from src.infrastructure.config.settings import settings
from src.modules.user import schemas as user_schemas
from src.modules.user.models import User
from src.modules.user.schemas import UserCreate, UserProfileRead, UserRead, UserUpdate


def test_the_password_field_documents_the_configured_policy():
    """OpenAPI describes the policy crudauth enforces, from the same object."""
    field = UserCreate.model_json_schema()["properties"]["password"]

    assert field["minLength"] == settings.PASSWORD_MIN_LENGTH
    assert f"At least {settings.PASSWORD_MIN_LENGTH} characters" in field["description"]


def test_the_signup_schema_offers_no_field_crudauth_gates():
    """A registration drops crudauth's privileged fields; this schema never asks for one."""
    assert not auth.repo.gated_register_fields(UserCreate.model_fields)


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


def test_the_read_schema_describes_a_row_rather_than_policing_it():
    """A row the app itself wrote has to be readable, whatever the signup rules were.

    OAuth can leave a one-character name, and the admin panel writes rows without
    the signup validators, so a read schema repeating those rules turns a valid
    row into a 500 on every response that includes it.
    """
    row = {
        "id": 1,
        "name": "A",
        "username": "x",
        "email": "someone@example.com",
        "profile_image_url": "https://example.com/a.jpg",
    }

    assert UserRead(**row).name == "A"


def test_the_profile_schema_reads_the_same_row():
    row = {"id": 1, "name": "A", "username": "x", "profile_image_url": "https://example.com/a.jpg"}

    assert UserProfileRead(**row).username == "x"


def test_the_profile_schema_carries_only_the_display_fields():
    """Another user's profile has no email address and none of the fields features contribute."""
    assert set(UserProfileRead.model_fields) == {"id", "name", "username", "profile_image_url"}


def _required_columns(model) -> tuple[str, ...]:
    return tuple(
        attribute.key for attribute in model.__mapper__.column_attrs if not any(column.nullable for column in attribute.columns)
    )


def test_the_guarded_names_are_the_models_required_columns():
    """``NOT_NULLABLE`` comes from the model, so a new column can't be forgotten."""
    assert UserUpdate.NOT_NULLABLE == _required_columns(User)


def test_reading_an_address_the_app_stored_is_not_validated_as_input():
    """The admin panel can write a local address; a read that refused it would answer 500."""
    row = UserRead(id=1, name="Ops", username="ops", email="ops@corp.local", profile_image_url="https://x/y.png")

    assert row.email == "ops@corp.local"
