"""API Key Management Models.

This module defines the database models for managing API keys,
permissions, and usage tracking for developer-facing products.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from ...infrastructure.database.models import TimestampMixin
from ...infrastructure.database.session import Base
from .enums import KeyPermissionAction, KeyPermissionResource


class APIKey(Base, TimestampMixin):
    """API key for programmatic access."""

    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("user.id"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    key_hash: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    key_prefix: Mapped[str] = mapped_column(String(20))
    permissions: Mapped[dict[str, Any]] = mapped_column(JSON, insert_default=dict)
    usage_limits: Mapped[dict[str, Any]] = mapped_column(JSON, insert_default=dict)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    last_used_ip: Mapped[str | None] = mapped_column(String(45), default=None)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    key_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)

    __table_args__ = (
        Index("idx_api_keys_user_active", "user_id", "is_active"),
        Index("idx_api_keys_prefix", "key_prefix"),
        Index("idx_api_keys_expires_at", "expires_at"),
    )


class KeyUsage(Base, TimestampMixin):
    """API key usage tracking for analytics and billing."""

    __tablename__ = "key_usage"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    api_key_id: Mapped[int] = mapped_column(Integer, ForeignKey("api_keys.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("user.id"), index=True)
    endpoint: Mapped[str] = mapped_column(String(255))
    method: Mapped[str] = mapped_column(String(10))
    status_code: Mapped[int] = mapped_column(Integer)
    tokens_used: Mapped[int | None] = mapped_column(Integer, default=None)
    cost_microcents: Mapped[int | None] = mapped_column(BigInteger, default=None)
    response_time_ms: Mapped[int | None] = mapped_column(Integer, default=None)
    ip_address: Mapped[str | None] = mapped_column(String(45), default=None)
    user_agent: Mapped[str | None] = mapped_column(Text, default=None)
    error_message: Mapped[str | None] = mapped_column(Text, default=None)
    usage_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)

    __table_args__ = (
        Index("idx_key_usage_key_created", "api_key_id", "created_at"),
        Index("idx_key_usage_user_created", "user_id", "created_at"),
        Index("idx_key_usage_endpoint", "endpoint"),
        Index("idx_key_usage_status", "status_code"),
    )


class KeyPermission(Base, TimestampMixin):
    """Granular permissions for API keys."""

    __tablename__ = "key_permissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    api_key_id: Mapped[int] = mapped_column(Integer, ForeignKey("api_keys.id", ondelete="CASCADE"), index=True)
    resource: Mapped[KeyPermissionResource] = mapped_column(index=True)  # KeyPermissionResource enum values
    action: Mapped[KeyPermissionAction] = mapped_column(index=True)  # KeyPermissionAction enum values
    conditions: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)
    is_allowed: Mapped[bool] = mapped_column(Boolean, default=True)

    __table_args__ = (
        Index("idx_key_permissions_key_resource", "api_key_id", "resource", "action", unique=True),
        Index("idx_key_permissions_resource_action", "resource", "action"),
    )
