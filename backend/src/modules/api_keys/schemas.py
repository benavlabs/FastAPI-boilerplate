"""Pydantic schemas for API key management validation."""

from datetime import datetime
from typing import Annotated, Any, ClassVar

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

from ..common.schemas import PartialUpdate, TimestampSchema, not_nullable_columns
from .enums import HTTPMethod, KeyPermissionAction, KeyPermissionResource
from .models import APIKey

VALID_HTTP_METHODS = {m.value for m in HTTPMethod}


class APIKeyBase(BaseModel):
    """Base schema for API key data."""

    name: Annotated[str, Field(min_length=1, max_length=100, description="Human-readable name for the API key")]
    permissions: dict[str, Any] = Field(default_factory=dict, description="Permission settings")
    usage_limits: dict[str, Any] = Field(default_factory=dict, description="Usage limits per key")
    expires_at: AwareDatetime | None = Field(default=None, description="Key expiration timestamp")
    key_metadata: dict[str, Any] | None = Field(default=None, description="Additional key metadata")


class APIKeyCreate(APIKeyBase):
    """Schema for creating a new API key."""

    pass


class APIKeyCreateInternal(APIKeyBase):
    """Internal schema for creating a new API key with additional fields."""

    user_id: int
    key_hash: str
    key_prefix: str


class APIKeyUpdate(PartialUpdate):
    """Schema for updating an existing API key."""

    NOT_NULLABLE: ClassVar[tuple[str, ...]] = not_nullable_columns(APIKey)

    name: Annotated[str, Field(min_length=1, max_length=100)] | None = None
    permissions: dict[str, Any] | None = None
    usage_limits: dict[str, Any] | None = None
    is_active: bool | None = None
    expires_at: AwareDatetime | None = None
    key_metadata: dict[str, Any] | None = None


class APIKeyRead(TimestampSchema, APIKeyBase):
    """Schema for reading API key data."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    key_prefix: str
    last_used_at: datetime | None
    last_used_ip: str | None
    is_active: bool


class APIKeyResponse(APIKeyRead):
    """Schema for API key creation response (includes full key)."""

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


class KeyUsageRead(TimestampSchema, KeyUsageBase):
    """Schema for reading key usage data."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    api_key_id: int
    user_id: int


class KeyPermissionBase(BaseModel):
    """Base schema for key permission data."""

    resource: Annotated[KeyPermissionResource, Field(description="Resource type")]
    action: Annotated[KeyPermissionAction, Field(description="Action type")]
    conditions: dict[str, Any] | None = Field(default=None, description="Additional conditions")
    is_allowed: bool = Field(default=True, description="Whether permission is granted")


class KeyPermissionCreate(KeyPermissionBase):
    """Schema for creating a new key permission."""

    api_key_id: int


class KeyPermissionUpdate(BaseModel):
    """Schema for updating an existing key permission."""

    conditions: dict[str, Any] | None = None
    is_allowed: bool | None = None


class KeyPermissionRead(TimestampSchema, KeyPermissionBase):
    """Schema for reading key permission data."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    api_key_id: int


class APIKeyWithPermissions(APIKeyRead):
    """Schema for API key with its permissions."""

    permissions_list: list[KeyPermissionRead] = Field(default_factory=list, description="Detailed permissions")


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
    resource: KeyPermissionResource = Field(description="Resource being accessed")
    action: KeyPermissionAction = Field(description="Action being performed")


class APIKeyValidationResponse(BaseModel):
    """Schema for API key validation responses."""

    is_valid: bool
    api_key_id: int | None = None
    user_id: int | None = None
    permissions: dict[str, Any] | None = None
    usage_limits: dict[str, Any] | None = None
    error_message: str | None = None
