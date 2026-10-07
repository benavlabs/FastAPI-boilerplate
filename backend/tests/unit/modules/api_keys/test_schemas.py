"""The update schema guards exactly the columns an API-key row requires."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from src.modules.api_keys.models import APIKey
from src.modules.api_keys.schemas import (
    APIKeyBase,
    APIKeyCreate,
    APIKeyRead,
    APIKeyUpdate,
    KeyUsageBase,
    KeyUsageCreate,
    KeyUsageRead,
)

STORED_KEY = {
    "id": 1,
    "user_id": 2,
    "name": "Stored Key",
    "key_prefix": "fai_test",
    "permissions": ["user.read"],
    "usage_limits": {},
    "expires_at": None,
    "key_metadata": None,
    "last_used_at": None,
    "last_used_ip": None,
    "is_active": True,
    "created_at": datetime.now(UTC),
    "updated_at": None,
}

STORED_USAGE = {
    "id": 1,
    "api_key_id": 2,
    "user_id": 3,
    "endpoint": "/api/v1/users/",
    "method": "GET",
    "status_code": 200,
    "tokens_used": None,
    "cost_microcents": None,
    "response_time_ms": None,
    "ip_address": None,
    "user_agent": None,
    "error_message": None,
    "usage_metadata": None,
    "created_at": datetime.now(UTC),
    "updated_at": None,
}


def _required_columns(model) -> tuple[str, ...]:
    return tuple(
        attribute.key for attribute in model.__mapper__.column_attrs if not any(column.nullable for column in attribute.columns)
    )


def test_the_guarded_names_are_the_models_required_columns():
    assert APIKeyUpdate.NOT_NULLABLE == _required_columns(APIKey)


@pytest.mark.parametrize("field", ["is_active", "permissions", "usage_limits", "name"])
def test_a_required_column_cannot_be_nulled(field: str):
    with pytest.raises(ValidationError, match="cannot be set to null"):
        APIKeyUpdate(**{field: None})


def test_a_nullable_column_still_accepts_null():
    assert APIKeyUpdate(expires_at=None).expires_at is None


class TestAReadSchemaDescribesTheRow:
    """A read schema that enforces input rules answers 500 on a row it would not accept."""

    def test_a_stored_empty_name_is_read_as_it_is(self):
        assert APIKeyRead.model_validate({**STORED_KEY, "name": ""}).name == ""

    def test_a_stored_expiry_without_an_offset_is_read_as_it_is(self):
        naive = datetime(2030, 1, 1, 12, 0, 0)

        assert APIKeyRead.model_validate({**STORED_KEY, "expires_at": naive}).expires_at == naive

    def test_a_stored_method_outside_the_enum_is_read_as_it_is(self):
        assert KeyUsageRead.model_validate({**STORED_USAGE, "method": "TRACE"}).method == "TRACE"

    def test_a_stored_status_code_outside_the_range_is_read_as_it_is(self):
        assert KeyUsageRead.model_validate({**STORED_USAGE, "status_code": 0}).status_code == 0

    def test_a_stored_name_the_registry_no_longer_knows_is_read_as_it_is(self):
        """A key keeps working after a permission is renamed out of the registry."""
        stored = APIKeyRead.model_validate({**STORED_KEY, "permissions": ["user.read", "widget.explode"]})

        assert stored.permissions == ["user.read", "widget.explode"]


class TestAKeysScopeIsRegistryPermissionNames:
    """A key is scoped by the same vocabulary a role carries and a route gates on."""

    def test_a_registered_name_is_accepted(self):
        assert APIKeyCreate(name="Key", permissions=["user.read"]).permissions == ["user.read"]

    def test_the_names_come_back_deduplicated_and_sorted(self):
        scope = APIKeyCreate(name="Key", permissions=["user.update", "user.read", "user.read"]).permissions

        assert scope == ["user.read", "user.update"]

    def test_an_unregistered_name_is_refused_on_create(self):
        with pytest.raises(ValidationError, match="widget.explode"):
            APIKeyCreate(name="Key", permissions=["widget.explode"])

    def test_an_unregistered_name_is_refused_on_update(self):
        with pytest.raises(ValidationError, match="widget.explode"):
            APIKeyUpdate(permissions=["user.read", "widget.explode"])

    def test_a_key_is_unscoped_by_default(self):
        assert APIKeyCreate(name="Key").permissions == []

    def test_an_object_is_refused_where_the_names_belong(self):
        """The shape an older version stored names nothing the registry knows."""
        with pytest.raises(ValidationError):
            APIKeyCreate(name="Key", permissions={"conversations": ["read"]})


class TestTheInputSchemasKeepTheirRules:
    """Dropping them from the read schemas must not drop them from what a caller sends."""

    def test_an_empty_name_is_still_refused_on_create(self):
        with pytest.raises(ValidationError):
            APIKeyCreate(name="")

    def test_an_expiry_without_an_offset_is_still_refused_on_create(self):
        with pytest.raises(ValidationError):
            APIKeyCreate(name="Key", expires_at=datetime(2030, 1, 1, 12, 0, 0))

    def test_a_method_outside_the_enum_is_still_refused_on_create(self):
        with pytest.raises(ValidationError, match="method must be one of"):
            KeyUsageCreate(api_key_id=1, user_id=2, endpoint="/api/v1/users/", method="TRACE", status_code=200)

    def test_a_status_code_outside_the_range_is_still_refused_on_create(self):
        with pytest.raises(ValidationError):
            KeyUsageCreate(api_key_id=1, user_id=2, endpoint="/api/v1/users/", method="GET", status_code=0)


@pytest.mark.parametrize(("described", "read"), [(APIKeyBase, APIKeyRead), (KeyUsageBase, KeyUsageRead)])
def test_a_read_schema_keeps_the_descriptions_the_document_shows(described, read):
    """Dropping the input rules must not drop what the OpenAPI response schema says."""
    descriptions = {name: field.description for name, field in described.model_fields.items() if field.description}

    assert descriptions
    assert {name: read.model_fields[name].description for name in descriptions} == descriptions


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("endpoint", "/api/v1/" + "p" * 400),
        ("ip_address", "x" * 60),
        ("tokens_used", -1),
        ("cost_microcents", -5),
        ("response_time_ms", -2),
    ],
)
def test_a_stored_usage_value_outside_the_input_rules_is_read_as_it_is(field: str, value):
    assert getattr(KeyUsageRead.model_validate({**STORED_USAGE, field: value}), field) == value
