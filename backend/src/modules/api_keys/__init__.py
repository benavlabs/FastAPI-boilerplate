"""API Key Management Module.

This module provides comprehensive API key management functionality
for developer-facing products and API-first business models.

Key Features:
- Secure API key generation and storage
- A scope of registry permission names per key
- Usage tracking per API key
- Key rotation and revocation
- Analytics and usage reporting
"""

from .crud import crud_api_keys, crud_key_usage
from .enums import HTTPMethod, KeyStatus, KeyType
from .models import APIKey, KeyUsage
from .schemas import (
    APIKeyBase,
    APIKeyCreate,
    APIKeyRead,
    APIKeyResponse,
    APIKeyUpdate,
    APIKeyValidationRequest,
    APIKeyValidationResponse,
    KeyUsageAnalytics,
    KeyUsageBase,
    KeyUsageCreate,
    KeyUsageRead,
    UserAPIKeySummary,
)
from .service import APIKeyService

__all__ = [
    # Models
    "APIKey",
    "KeyUsage",
    # Schemas
    "APIKeyBase",
    "APIKeyCreate",
    "APIKeyRead",
    "APIKeyResponse",
    "APIKeyUpdate",
    "KeyUsageBase",
    "KeyUsageCreate",
    "KeyUsageRead",
    "KeyUsageAnalytics",
    "UserAPIKeySummary",
    "APIKeyValidationRequest",
    "APIKeyValidationResponse",
    # CRUD
    "crud_api_keys",
    "crud_key_usage",
    # Service
    "APIKeyService",
    # Enums
    "HTTPMethod",
    "KeyStatus",
    "KeyType",
]
