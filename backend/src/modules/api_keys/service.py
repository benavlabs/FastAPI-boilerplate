"""API key management service for developer-facing products."""

import base64
import binascii
import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from fastcrud.types import GetMultiResponseDict
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.logging import get_logger
from ..common.exceptions import PermissionDeniedError, ResourceNotFoundError
from .crud import crud_api_keys, crud_key_permissions, crud_key_usage
from .enums import KeyPermissionAction, KeyPermissionResource
from .models import APIKey, KeyUsage
from .schemas import (
    APIKeyCreate,
    APIKeyCreateInternal,
    APIKeyRead,
    APIKeyUpdate,
    APIKeyValidationResponse,
    KeyUsageCreate,
    KeyUsageRead,
)

logger = get_logger()

_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1
_SCRYPT_DKLEN = 32


class APIKeyService:
    """Service for managing API keys, permissions, and usage tracking.

    Provides high-level operations for API key lifecycle management,
    permission validation, usage tracking, and analytics.
    """

    def __init__(self):
        """Initialize API key service."""
        self.key_prefix_length = 8
        self.key_length = 48

    def _generate_api_key(self) -> tuple[str, str, str]:
        """Generate a new API key with prefix and hash.

        Returns:
            Tuple of (full_key, prefix, hash)
        """
        raw_key = secrets.token_urlsafe(self.key_length)
        prefix = raw_key[: self.key_prefix_length]
        api_key = f"fai_{prefix}_{raw_key[self.key_prefix_length :]}"
        key_hash = self._hash_api_key(api_key)

        return api_key, prefix, key_hash

    def _hash_api_key(self, api_key: str) -> str:
        """Hash an API key for storage using scrypt with a per-row salt.

        Stored format: ``scrypt$N$r$p$salt_b64$derived_b64``. Non-deterministic;
        DB lookup uses ``key_prefix`` (already indexed) instead of ``key_hash``.
        """
        salt = secrets.token_bytes(16)
        derived = hashlib.scrypt(
            api_key.encode("utf-8"),
            salt=salt,
            n=_SCRYPT_N,
            r=_SCRYPT_R,
            p=_SCRYPT_P,
            dklen=_SCRYPT_DKLEN,
        )
        salt_b64 = base64.b64encode(salt).decode("ascii")
        derived_b64 = base64.b64encode(derived).decode("ascii")
        return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${salt_b64}${derived_b64}"

    def _verify_api_key(self, api_key: str, stored_hash: str) -> bool:
        """Verify a candidate ``api_key`` against a stored scrypt hash."""
        try:
            scheme, n_str, r_str, p_str, salt_b64, derived_b64 = stored_hash.split("$", 5)
        except ValueError:
            return False
        if scheme != "scrypt":
            return False
        try:
            n = int(n_str)
            r = int(r_str)
            p = int(p_str)
            salt = base64.b64decode(salt_b64)
            expected = base64.b64decode(derived_b64)
        except (ValueError, binascii.Error):
            return False
        actual = hashlib.scrypt(
            api_key.encode("utf-8"),
            salt=salt,
            n=n,
            r=r,
            p=p,
            dklen=len(expected),
        )
        return hmac.compare_digest(actual, expected)

    async def create_api_key(
        self,
        user_id: int,
        key_data: APIKeyCreate,
        db: AsyncSession,
    ) -> dict[str, Any]:
        """Create a new API key for a user.

        Args:
            user_id: User ID
            key_data: API key creation data
            db: Database session

        Returns:
            Created API key with full key (only shown once)
        """
        api_key, prefix, key_hash = self._generate_api_key()

        key_dict = key_data.model_dump()
        key_dict.update(
            {
                "user_id": user_id,
                "key_hash": key_hash,
                "key_prefix": prefix,
            }
        )

        key_internal = APIKeyCreateInternal(**key_dict)
        created_key = await crud_api_keys.create(db=db, object=key_internal, schema_to_select=APIKeyRead)

        if not created_key:
            raise ValueError("Failed to create API key")

        logger.info(f"Created API key {created_key['id']} for user {user_id}")

        response_data = created_key.copy()
        response_data["api_key"] = api_key

        return response_data

    async def get_user_api_keys(
        self,
        user_id: int,
        db: AsyncSession,
        active_only: bool = True,
        limit: int = 50,
        offset: int = 0,
    ) -> GetMultiResponseDict:
        """Get all API keys for a user.

        Args:
            user_id: User ID
            db: Database session
            active_only: Whether to return only active keys

        Returns:
            List of API keys
        """
        if active_only:
            return await crud_api_keys.get_multi(
                db=db,
                limit=limit,
                offset=offset,
                sort_columns="created_at",
                sort_orders="desc",
                user_id=user_id,
                is_active=True,
                schema_to_select=APIKeyRead,
            )
        else:
            return await crud_api_keys.get_multi(
                db=db,
                limit=limit,
                offset=offset,
                sort_columns="created_at",
                sort_orders="desc",
                user_id=user_id,
                schema_to_select=APIKeyRead,
            )

    async def get_api_key(
        self,
        key_id: int,
        user_id: int,
        db: AsyncSession,
    ) -> dict[str, Any]:
        """Get a specific API key for a user.

        Args:
            key_id: API key ID
            user_id: User ID (for ownership verification)
            db: Database session

        Returns:
            API key data

        Raises:
            ResourceNotFoundError: If key not found
            PermissionDeniedError: If user doesn't own the key
        """
        key = await crud_api_keys.get(db=db, id=key_id, schema_to_select=APIKeyRead)

        if not key:
            raise ResourceNotFoundError("API key not found")

        if key["user_id"] != user_id:
            raise PermissionDeniedError("Access denied to this API key")

        return key

    async def update_api_key(
        self,
        key_id: int,
        user_id: int,
        update_data: APIKeyUpdate,
        db: AsyncSession,
    ) -> dict[str, Any]:
        """Update an API key.

        Args:
            key_id: API key ID
            user_id: User ID (for ownership verification)
            update_data: Update data
            db: Database session

        Returns:
            Updated API key data
        """
        await self.get_api_key(key_id=key_id, user_id=user_id, db=db)

        update_dict = update_data.model_dump(exclude_unset=True)
        updated_key = await crud_api_keys.update(
            db=db,
            object=update_dict,
            id=key_id,
            return_columns=list(APIKeyRead.model_fields.keys()),
        )

        logger.info(f"Updated API key {key_id} for user {user_id}")

        if updated_key is None:
            updated_key = await crud_api_keys.get(db=db, id=key_id, schema_to_select=APIKeyRead)

        if updated_key is None:
            raise ResourceNotFoundError("API key not found after update")

        return updated_key

    async def delete_api_key(
        self,
        key_id: int,
        user_id: int,
        db: AsyncSession,
    ) -> None:
        """Delete (deactivate) an API key.

        Args:
            key_id: API key ID
            user_id: User ID (for ownership verification)
            db: Database session
        """
        await self.get_api_key(key_id=key_id, user_id=user_id, db=db)

        await crud_api_keys.update(
            db=db,
            object={"is_active": False},
            id=key_id,
        )

        logger.info(f"Deactivated API key {key_id} for user {user_id}")

    async def validate_api_key(
        self,
        api_key: str,
        resource: str,
        action: str,
        db: AsyncSession,
    ) -> APIKeyValidationResponse:
        """Validate an API key and check permissions.

        Args:
            api_key: API key to validate
            resource: Resource being accessed
            action: Action being performed
            db: Database session

        Returns:
            Validation response with key details and permissions
        """
        prefix_start = len("fai_")
        prefix_end = prefix_start + self.key_prefix_length
        if not api_key.startswith("fai_") or len(api_key) <= prefix_end or api_key[prefix_end] != "_":
            return APIKeyValidationResponse(
                is_valid=False,
                error_message="Invalid API key",
            )
        prefix = api_key[prefix_start:prefix_end]

        result = await db.execute(select(APIKey).where(APIKey.key_prefix == prefix).execution_options(populate_existing=True))
        candidates = result.scalars().all()

        matched: APIKey | None = None
        for candidate in candidates:
            if self._verify_api_key(api_key, candidate.key_hash):
                matched = candidate
                break

        if matched is None:
            return APIKeyValidationResponse(
                is_valid=False,
                error_message="Invalid API key",
            )

        key = APIKeyRead.model_validate(matched).model_dump()

        if not key["is_active"]:
            return APIKeyValidationResponse(
                is_valid=False,
                error_message="API key is inactive",
            )

        if key["expires_at"] and key["expires_at"] < datetime.now(UTC):
            return APIKeyValidationResponse(
                is_valid=False,
                error_message="API key has expired",
            )

        has_permission = await self._check_permission(
            api_key_id=key["id"],
            resource=resource,
            action=action,
            db=db,
        )

        if not has_permission:
            return APIKeyValidationResponse(
                is_valid=False,
                error_message=f"No permission for {action} on {resource}",
            )

        await crud_api_keys.update(
            db=db,
            object={
                "last_used_at": datetime.now(UTC),
            },
            id=key["id"],
        )

        return APIKeyValidationResponse(
            is_valid=True,
            api_key_id=key["id"],
            user_id=key["user_id"],
            permissions=key["permissions"],
            usage_limits=key["usage_limits"],
        )

    async def record_usage(
        self,
        api_key_id: int,
        user_id: int,
        usage_data: KeyUsageCreate,
        db: AsyncSession,
    ) -> dict[str, Any]:
        """Record API key usage for analytics and billing.

        Args:
            api_key_id: API key ID
            user_id: User ID
            usage_data: Usage data
            db: Database session

        Returns:
            Created usage record
        """
        if usage_data.api_key_id != api_key_id or usage_data.user_id != user_id:
            usage_dict = usage_data.model_dump()
            usage_dict.update(
                {
                    "api_key_id": api_key_id,
                    "user_id": user_id,
                }
            )
            usage_data = KeyUsageCreate(**usage_dict)

        usage_record = await crud_key_usage.create(db=db, object=usage_data, schema_to_select=KeyUsageRead)

        if not usage_record:
            raise ValueError("Failed to create usage record")

        return usage_record

    async def get_key_usage(
        self,
        key_id: int,
        user_id: int,
        db: AsyncSession,
        limit: int = 100,
        offset: int = 0,
    ) -> GetMultiResponseDict:
        """Get usage history for an API key.

        Args:
            key_id: API key ID
            user_id: User ID (for ownership verification)
            db: Database session
            limit: Maximum number of records
            offset: Number of records to skip

        Returns:
            List of usage records
        """
        await self.get_api_key(key_id=key_id, user_id=user_id, db=db)

        return await crud_key_usage.get_multi(
            db=db,
            limit=limit,
            offset=offset,
            sort_columns="created_at",
            sort_orders="desc",
            api_key_id=key_id,
            schema_to_select=KeyUsageRead,
        )

    async def get_usage_analytics(
        self,
        key_id: int,
        user_id: int,
        db: AsyncSession,
        days: int = 30,
    ) -> dict[str, Any]:
        """Get usage analytics for an API key.

        Args:
            key_id: API key ID
            user_id: User ID (for ownership verification)
            db: Database session
            days: Number of days to analyze

        Returns:
            Usage analytics
        """
        await self.get_api_key(key_id=key_id, user_id=user_id, db=db)

        since_date = datetime.now(UTC) - timedelta(days=days)

        in_window = (KeyUsage.api_key_id == key_id, KeyUsage.created_at >= since_date)
        successful = func.count().filter(KeyUsage.status_code.between(200, 299))
        tokens = func.coalesce(func.sum(KeyUsage.tokens_used), 0)
        cost = func.coalesce(func.sum(KeyUsage.cost_microcents), 0)

        totals = (
            await db.execute(
                select(func.count(), successful, tokens, cost, func.avg(KeyUsage.response_time_ms)).where(*in_window)
            )
        ).one()
        total_requests, successful_requests, total_tokens, total_cost, avg_response_time = totals

        endpoint_count = func.count().label("count")
        endpoint_rows = await db.execute(
            select(KeyUsage.endpoint, endpoint_count)
            .where(*in_window)
            .group_by(KeyUsage.endpoint)
            .order_by(endpoint_count.desc(), KeyUsage.endpoint)
            .limit(10)
        )

        error_rows = await db.execute(
            select(KeyUsage.status_code, func.count())
            .where(*in_window, KeyUsage.status_code >= 400)
            .group_by(KeyUsage.status_code)
            .order_by(KeyUsage.status_code)
        )

        day = func.date(func.timezone("UTC", KeyUsage.created_at)).label("day")
        daily_rows = await db.execute(
            select(day, func.count(), successful, tokens, cost).where(*in_window).group_by(day).order_by(day)
        )

        return {
            "api_key_id": key_id,
            "total_requests": total_requests,
            "successful_requests": successful_requests,
            "failed_requests": total_requests - successful_requests,
            "total_tokens": int(total_tokens),
            "total_cost_microcents": int(total_cost),
            "average_response_time_ms": float(avg_response_time) if avg_response_time is not None else None,
            "most_used_endpoints": [{"endpoint": endpoint, "count": count} for endpoint, count in endpoint_rows],
            "error_breakdown": {str(status_code): count for status_code, count in error_rows},
            "usage_by_day": [
                {
                    "date": row_day.isoformat(),
                    "requests": requests,
                    "successful_requests": day_successful,
                    "failed_requests": requests - day_successful,
                    "tokens": int(day_tokens),
                    "cost_microcents": int(day_cost),
                }
                for row_day, requests, day_successful, day_tokens, day_cost in daily_rows
            ],
        }

    async def get_user_summary(
        self,
        user_id: int,
        db: AsyncSession,
    ) -> dict[str, Any]:
        """Get comprehensive API key summary for a user.

        Args:
            user_id: User ID
            db: Database session

        Returns:
            User API key summary
        """
        keys_result = await self.get_user_api_keys(user_id=user_id, db=db, active_only=False)
        keys_data = keys_result.get("data", []) if isinstance(keys_result, dict) else []

        total_requests_result = await crud_key_usage.count(db=db, user_id=user_id)
        total_requests = total_requests_result if isinstance(total_requests_result, int) else 0

        total_cost = await self.sum_user_usage_cost(user_id=user_id, db=db)
        total_keys, active_keys = await self.count_user_api_keys(user_id=user_id, db=db)

        return {
            "user_id": user_id,
            "total_keys": total_keys,
            "active_keys": active_keys,
            "total_requests": total_requests,
            "total_cost_microcents": total_cost,
            "keys": keys_data,
        }

    async def sum_user_usage_cost(self, user_id: int, db: AsyncSession) -> int:
        """Total ``cost_microcents`` across every key-usage record of a user.

        Args:
            user_id: User ID
            db: Database session

        Returns:
            The summed cost, ``0`` when the user has no usage.
        """
        stmt = select(func.coalesce(func.sum(KeyUsage.cost_microcents), 0)).where(KeyUsage.user_id == user_id)
        return int((await db.execute(stmt)).scalar_one() or 0)

    async def count_user_api_keys(self, user_id: int, db: AsyncSession) -> tuple[int, int]:
        """Count a user's API keys, in total and active only.

        Args:
            user_id: User ID
            db: Database session

        Returns:
            ``(total_keys, active_keys)``.
        """
        stmt = select(func.count(), func.count().filter(APIKey.is_active)).where(APIKey.user_id == user_id)
        total, active = (await db.execute(stmt)).one()
        return int(total), int(active)

    async def _check_permission(
        self,
        api_key_id: int,
        resource: str,
        action: str,
        db: AsyncSession,
    ) -> bool:
        """Check if an API key has permission for a resource/action.

        Args:
            api_key_id: API key ID
            resource: Resource type
            action: Action type
            db: Database session

        Returns:
            True if permission granted, False otherwise
        """
        resource_enum = None
        action_enum = None

        try:
            resource_enum = KeyPermissionResource(resource)
        except ValueError:
            pass

        try:
            action_enum = KeyPermissionAction(action)
        except ValueError:
            pass

        permission = None
        if resource_enum and action_enum:
            permission = await crud_key_permissions.get(
                db=db,
                api_key_id=api_key_id,
                resource=resource_enum,
                action=action_enum,
            )

        if not permission and action_enum:
            permission = await crud_key_permissions.get(
                db=db,
                api_key_id=api_key_id,
                resource=KeyPermissionResource.WILDCARD,
                action=action_enum,
            )

        if not permission and resource_enum:
            permission = await crud_key_permissions.get(
                db=db,
                api_key_id=api_key_id,
                resource=resource_enum,
                action=KeyPermissionAction.WILDCARD,
            )

        if not permission:
            permission = await crud_key_permissions.get(
                db=db,
                api_key_id=api_key_id,
                resource=KeyPermissionResource.WILDCARD,
                action=KeyPermissionAction.WILDCARD,
            )

        return permission["is_allowed"] if permission else False
