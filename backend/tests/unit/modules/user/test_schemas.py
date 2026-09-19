"""Unit tests for the User schemas."""

from src.infrastructure.config.settings import settings
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
