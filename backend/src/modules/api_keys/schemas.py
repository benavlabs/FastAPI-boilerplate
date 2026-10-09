"""Pydantic schemas for API key management validation."""

from datetime import datetime
from typing import Annotated, Any, ClassVar

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

from ...infrastructure.permissions import registered_permissions
from ..common.schemas import EncodableText, PartialUpdate, TimestampSchema, not_nullable_columns, within_utc_range
from .enums import HTTPMethod
from .models import APIKey

VALID_HTTP_METHODS = {m.value for m in HTTPMethod}


class APIKeyBase(EncodableText):
    """Base schema for API key data."""

    _expiry_within_range = field_validator("expires_at")(within_utc_range)

    name: Annotated[str, Field(min_length=1, max_length=100, description="Human-readable name for the API key")]
    permissions: list[str] = Field(
        default_factory=list,
        description="Registry permission names the key is scoped to",
        examples=[["user.read", "user.update"]],
    )
    usage_limits: dict[str, Any] = Field(default_factory=dict, description="Usage limits per key")
    expires_at: AwareDatetime | None = Field(default=None, description="Key expiration timestamp")
    key_metadata: dict[str, Any] | None = Field(default=None, description="Additional key metadata")

    @field_validator("permissions")
    @classmethod
    def _registered(cls, names: list[str]) -> list[str]:
        return registered_permissions(names)


class APIKeyCreate(APIKeyBase):
    """Schema for creating a new API key."""

    pass


class APIKeyCreateInternal(APIKeyBase):
    """Internal schema for creating a new API key with additional fields."""

    user_id: int
    key_hash: str
    key_prefix: str


class APIKeyUpdate(EncodableText, PartialUpdate):
    """Schema for updating an existing API key."""

    _expiry_within_range = field_validator("expires_at")(within_utc_range)

    NOT_NULLABLE: ClassVar[tuple[str, ...]] = not_nullable_columns(APIKey)

    name: Annotated[str, Field(min_length=1, max_length=100)] | None = None
    permissions: list[str] | None = None
    usage_limits: dict[str, Any] | None = None
    is_active: bool | None = None
    expires_at: AwareDatetime | None = None
    key_metadata: dict[str, Any] | None = None

    @field_validator("permissions")
    @classmethod
    def _registered(cls, names: list[str] | None) -> list[str] | None:
        return None if names is None else registered_permissions(names)


class APIKeyRead(TimestampSchema):
    """An API key row as it is stored, with none of the input rules from ``APIKeyBase``."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    name: str = Field(description="Human-readable name for the API key")
    key_prefix: str
    permissions: list[str] = Field(description="Registry permission names the key is scoped to")
    usage_limits: dict[str, Any] = Field(description="Usage limits per key")
    expires_at: datetime | None = Field(description="Key expiration timestamp")
    key_metadata: dict[str, Any] | None = Field(description="Additional key metadata")
    last_used_at: datetime | None
    last_used_ip: str | None
    is_active: bool


class APIKeyResponse(APIKeyRead):
    """Schema for API key creation response: the key itself, and the row as read.

    Follows ``APIKeyRead``, with ``key_metadata`` and ``last_used_ip`` excluded from
    the response.
    """

    key_metadata: dict[str, Any] | None = Field(default=None, exclude=True)
    last_used_ip: str | None = Field(default=None, exclude=True)
    api_key: str = Field(description="Full API key - only shown once during creation")


class KeyUsageBase(BaseModel):
    """Base schema for key usage data."""

    endpoint: Annotated[str, Field(max_length=255, description="API endpoint used")]
    method: Annotated[str, Field(max_length=10, description="HTTP method")]
    status_code: Annotated[int, Field(ge=100, le=599, description="Response status code")]
    tokens_used: int | None = Field(default=None, ge=0, description="AI tokens consumed")

    cost_microcents: int | None = Field(default=None, ge=0, description="Cost in microcents")
    response_time_ms: int | None = Field(default=None, ge=0, description="Response time in milliseconds")
    ip_address: str | None = Field(default=None, max_length=45, description="Client IP address")
    user_agent: str | None = Field(default=None, description="Client user agent")
    error_message: str | None = Field(default=None, description="Error details if any")
    usage_metadata: dict[str, Any] | None = Field(default=None, description="Additional usage metadata")

    @field_validator("method")
    @classmethod
    def validate_method(cls, v: str) -> str:
        """Validate method against HTTPMethod enum values."""
        v_upper = v.upper()
        if v_upper not in VALID_HTTP_METHODS:
            raise ValueError(f"method must be one of: {sorted(VALID_HTTP_METHODS)}")
        return v_upper


class KeyUsageCreate(KeyUsageBase):
    """Schema for creating a new key usage record."""

    api_key_id: int
    user_id: int


class KeyUsageRead(TimestampSchema):
    """A usage row as it is stored, with none of the input rules from ``KeyUsageBase``."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    api_key_id: int
    user_id: int
    endpoint: str = Field(description="API endpoint used")
    method: str = Field(description="HTTP method")
    status_code: int = Field(description="Response status code")
    tokens_used: int | None = Field(description="AI tokens consumed")
    cost_microcents: int | None = Field(description="Cost in microcents")
    response_time_ms: int | None = Field(description="Response time in milliseconds")
    ip_address: str | None = Field(description="Client IP address")
    user_agent: str | None = Field(description="Client user agent")
    error_message: str | None = Field(description="Error details if any")
    usage_metadata: dict[str, Any] | None = Field(description="Additional usage metadata")


class KeyUsageAnalytics(BaseModel):
    """Schema for key usage analytics."""

    api_key_id: int
    total_requests: int
    successful_requests: int
    failed_requests: int
    total_tokens: int
    total_cost_microcents: int
    average_response_time_ms: float | None
    most_used_endpoints: list[dict[str, Any]]
    error_breakdown: dict[str, int]
    usage_by_day: list[dict[str, Any]]


class UserAPIKeySummary(BaseModel):
    """Schema for user API key summary."""

    user_id: int
    total_keys: int
    active_keys: int
    total_requests: int
    total_cost_microcents: int
    keys: list[APIKeyRead]


class APIKeyValidationRequest(BaseModel):
    """Schema for API key validation requests."""

    api_key: str = Field(description="API key to validate")


class APIKeyValidationResponse(BaseModel):
    """Schema for API key validation responses."""

    is_valid: bool
    api_key_id: int | None = None
    user_id: int | None = None
    permissions: list[str] | None = None
    usage_limits: dict[str, Any] | None = None
    error_message: str | None = None
