"""Tests for API key management service."""

from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.api_keys.crud import crud_api_keys, crud_key_permissions
from src.modules.api_keys.enums import KeyPermissionAction, KeyPermissionResource
from src.modules.api_keys.models import KeyUsage
from src.modules.api_keys.schemas import (
    APIKeyCreate,
    APIKeyCreateInternal,
    APIKeyUpdate,
    KeyPermissionCreate,
    KeyUsageCreate,
)
from src.modules.api_keys.service import APIKeyService
from src.modules.common.exceptions import PermissionDeniedError, ResourceNotFoundError


@pytest.fixture
def api_key_service():
    """Create API key service instance."""
    return APIKeyService()


@pytest_asyncio.fixture
async def test_api_key(api_key_service, db_session: AsyncSession, test_user: dict):
    """Create a test API key."""
    key_data = APIKeyCreate(
        name="Test API Key", permissions={"read": True, "write": True}, usage_limits={"requests_per_day": 1000}
    )

    response = await api_key_service.create_api_key(user_id=test_user["id"], key_data=key_data, db=db_session)

    return response


@pytest.mark.asyncio
async def test_create_api_key(api_key_service, db_session: AsyncSession, test_user: dict):
    """Test creating a new API key."""
    key_data = APIKeyCreate(name="Test Key", permissions={"read": True, "write": True}, usage_limits={"requests_per_day": 1000})

    response = await api_key_service.create_api_key(user_id=test_user["id"], key_data=key_data, db=db_session)

    assert response["name"] == "Test Key"
    assert response["user_id"] == test_user["id"]
    assert response["is_active"] is True
    assert response["api_key"].startswith("fai_")
    assert len(response["api_key"]) > 20  # Should be long enough
    assert response["key_prefix"] is not None
    assert len(response["key_prefix"]) == 8


@pytest.mark.asyncio
async def test_api_key_generation_unique(api_key_service):
    """Test that API key generation produces unique keys."""
    key1, prefix1, hash1 = api_key_service._generate_api_key()
    key2, prefix2, hash2 = api_key_service._generate_api_key()

    assert key1 != key2
    assert prefix1 != prefix2
    assert hash1 != hash2
    assert key1.startswith("fai_")
    assert key2.startswith("fai_")


@pytest.mark.asyncio
async def test_get_user_api_keys(api_key_service, db_session: AsyncSession, test_user: dict, test_api_key):
    """Test getting user's API keys."""
    result = await api_key_service.get_user_api_keys(user_id=test_user["id"], db=db_session)
    keys = result.get("data", []) if isinstance(result, dict) else []

    assert len(keys) >= 1
    key = keys[0]
    assert key["name"] == "Test API Key"
    assert key["user_id"] == test_user["id"]
    assert key["is_active"] is True
    # API key should not be included in read response
    assert "api_key" not in key


@pytest.mark.asyncio
async def test_get_user_api_keys_active_only(api_key_service, db_session: AsyncSession, test_user: dict, test_api_key):
    """Test getting only active API keys."""
    # Deactivate the test key
    await api_key_service.delete_api_key(key_id=test_api_key["id"], user_id=test_user["id"], db=db_session)

    # Should return no active keys
    active_result = await api_key_service.get_user_api_keys(user_id=test_user["id"], db=db_session, active_only=True)
    active_keys = active_result.get("data", []) if isinstance(active_result, dict) else []

    # Should return all keys including inactive
    all_result = await api_key_service.get_user_api_keys(user_id=test_user["id"], db=db_session, active_only=False)
    all_keys = all_result.get("data", []) if isinstance(all_result, dict) else []

    assert len(active_keys) == 0
    assert len(all_keys) >= 1


@pytest.mark.asyncio
async def test_get_api_key_success(api_key_service, db_session: AsyncSession, test_user: dict, test_api_key):
    """Test getting a specific API key."""
    key = await api_key_service.get_api_key(key_id=test_api_key["id"], user_id=test_user["id"], db=db_session)

    assert key["id"] == test_api_key["id"]
    assert key["name"] == "Test API Key"
    assert key["user_id"] == test_user["id"]


@pytest.mark.asyncio
async def test_get_api_key_not_found(api_key_service, db_session: AsyncSession, test_user: dict):
    """Test getting non-existent API key."""
    with pytest.raises(ResourceNotFoundError):
        await api_key_service.get_api_key(key_id=99999, user_id=test_user["id"], db=db_session)


@pytest.mark.asyncio
async def test_get_api_key_permission_denied(
    api_key_service, db_session: AsyncSession, test_user: dict, test_user_2: dict, test_api_key
):
    """Test getting API key owned by different user."""
    with pytest.raises(PermissionDeniedError):
        await api_key_service.get_api_key(key_id=test_api_key["id"], user_id=test_user_2["id"], db=db_session)


@pytest.mark.asyncio
async def test_update_api_key(api_key_service, db_session: AsyncSession, test_user: dict, test_api_key):
    """Test updating an API key."""
    update_data = APIKeyUpdate(name="Updated Key Name")

    updated_key = await api_key_service.update_api_key(
        key_id=test_api_key["id"], user_id=test_user["id"], update_data=update_data, db=db_session
    )

    assert updated_key["name"] == "Updated Key Name"
    assert updated_key["id"] == test_api_key["id"]


@pytest.mark.asyncio
async def test_delete_api_key(api_key_service, db_session: AsyncSession, test_user: dict, test_api_key):
    """Test deleting (deactivating) an API key."""
    await api_key_service.delete_api_key(key_id=test_api_key["id"], user_id=test_user["id"], db=db_session)

    # Key should still exist but be inactive
    key = await api_key_service.get_api_key(key_id=test_api_key["id"], user_id=test_user["id"], db=db_session)

    assert key["is_active"] is False


@pytest.mark.asyncio
async def test_validate_api_key_success(api_key_service, db_session: AsyncSession, test_user: dict, test_api_key):
    """Test successful API key validation."""
    # Add permission for the key
    permission_data = KeyPermissionCreate(
        api_key_id=test_api_key["id"],
        resource=KeyPermissionResource.CONVERSATIONS,
        action=KeyPermissionAction.READ,
        is_allowed=True,
    )
    await crud_key_permissions.create(db=db_session, object=permission_data)

    validation = await api_key_service.validate_api_key(
        api_key=test_api_key["api_key"], resource="conversations", action="read", db=db_session
    )

    assert validation.is_valid is True
    assert validation.api_key_id == test_api_key["id"]
    assert validation.user_id == test_user["id"]
    assert validation.error_message is None


@pytest.mark.asyncio
async def test_validate_api_key_invalid(api_key_service, db_session: AsyncSession):
    """Test validation with invalid API key."""
    validation = await api_key_service.validate_api_key(
        api_key="fai_invalid_key_12345", resource="conversations", action="read", db=db_session
    )

    assert validation.is_valid is False
    assert "Invalid API key" in validation.error_message


@pytest.mark.asyncio
async def test_validate_api_key_inactive(api_key_service, db_session: AsyncSession, test_user: dict, test_api_key):
    """Test validation with inactive API key."""
    # Deactivate the key
    await api_key_service.delete_api_key(key_id=test_api_key["id"], user_id=test_user["id"], db=db_session)

    validation = await api_key_service.validate_api_key(
        api_key=test_api_key["api_key"], resource="conversations", action="read", db=db_session
    )

    assert validation.is_valid is False
    assert "inactive" in validation.error_message


@pytest.mark.asyncio
async def test_validate_api_key_expired(api_key_service, db_session: AsyncSession, test_user: dict):
    """Test validation with expired API key."""
    # Create key with past expiration

    key_data = APIKeyCreate(
        name="Expired Key",
        expires_at=datetime.now(UTC) - timedelta(days=1),  # Already expired
    )

    expired_key = await api_key_service.create_api_key(user_id=test_user["id"], key_data=key_data, db=db_session)

    validation = await api_key_service.validate_api_key(
        api_key=expired_key["api_key"], resource="conversations", action="read", db=db_session
    )

    assert validation.is_valid is False
    assert "expired" in validation.error_message


@pytest.mark.asyncio
async def test_validate_api_key_no_permission(api_key_service, db_session: AsyncSession, test_user: dict, test_api_key):
    """Test validation with no permissions."""
    validation = await api_key_service.validate_api_key(
        api_key=test_api_key["api_key"], resource="admin", action="delete", db=db_session
    )

    assert validation.is_valid is False
    assert "No permission" in validation.error_message


@pytest.mark.asyncio
async def test_wildcard_permissions(api_key_service, db_session: AsyncSession, test_user: dict, test_api_key):
    """Test wildcard permission validation."""
    # Add wildcard permission
    permission_data = KeyPermissionCreate(
        api_key_id=test_api_key["id"],
        resource=KeyPermissionResource.WILDCARD,
        action=KeyPermissionAction.WILDCARD,
        is_allowed=True,
    )
    await crud_key_permissions.create(db=db_session, object=permission_data)

    validation = await api_key_service.validate_api_key(
        api_key=test_api_key["api_key"], resource="any_resource", action="any_action", db=db_session
    )

    assert validation.is_valid is True


@pytest.mark.asyncio
async def test_record_usage(api_key_service, db_session: AsyncSession, test_user: dict, test_api_key):
    """Test recording API key usage."""
    usage_data = KeyUsageCreate(
        api_key_id=test_api_key["id"],
        user_id=test_user["id"],
        endpoint="/api/v1/conversations",
        method="POST",
        status_code=201,
        response_time_ms=150,
        tokens_used=25,
        cost_microcents=5000,  # $0.05
        user_agent="test-client/1.0",
    )

    usage_record = await api_key_service.record_usage(
        api_key_id=test_api_key["id"], user_id=test_user["id"], usage_data=usage_data, db=db_session
    )

    assert usage_record["api_key_id"] == test_api_key["id"]
    assert usage_record["user_id"] == test_user["id"]
    assert usage_record["endpoint"] == "/api/v1/conversations"
    assert usage_record["status_code"] == 201
    assert usage_record["tokens_used"] == 25
    assert usage_record["cost_microcents"] == 5000


@pytest.mark.asyncio
async def test_get_key_usage(api_key_service, db_session: AsyncSession, test_user: dict, test_api_key):
    """Test getting API key usage history."""
    # Record some usage
    usage_data = KeyUsageCreate(
        api_key_id=test_api_key["id"],
        user_id=test_user["id"],
        endpoint="/api/v1/test",
        method="GET",
        status_code=200,
        response_time_ms=100,
    )

    await api_key_service.record_usage(
        api_key_id=test_api_key["id"], user_id=test_user["id"], usage_data=usage_data, db=db_session
    )

    result = await api_key_service.get_key_usage(key_id=test_api_key["id"], user_id=test_user["id"], db=db_session)
    usage_history = result.get("data", []) if isinstance(result, dict) else []

    assert len(usage_history) >= 1
    usage = usage_history[0]
    assert usage["api_key_id"] == test_api_key["id"]
    assert usage["endpoint"] == "/api/v1/test"


@pytest.mark.asyncio
async def test_get_usage_analytics(api_key_service, db_session: AsyncSession, test_user: dict, test_api_key):
    """Test getting usage analytics for API key."""
    # Record multiple usage entries
    endpoints = ["/api/v1/test1", "/api/v1/test2", "/api/v1/test1"]
    status_codes = [200, 201, 500]

    for i, endpoint in enumerate(endpoints):
        usage_data = KeyUsageCreate(
            api_key_id=test_api_key["id"],
            user_id=test_user["id"],
            endpoint=endpoint,
            method="GET",
            status_code=status_codes[i],
            response_time_ms=100 + i * 50,
            tokens_used=10 + i * 5,
            cost_microcents=1000 * (i + 1),
        )

        await api_key_service.record_usage(
            api_key_id=test_api_key["id"], user_id=test_user["id"], usage_data=usage_data, db=db_session
        )

    analytics = await api_key_service.get_usage_analytics(key_id=test_api_key["id"], user_id=test_user["id"], db=db_session)

    assert analytics["api_key_id"] == test_api_key["id"]
    assert analytics["total_requests"] == 3
    assert analytics["successful_requests"] == 2  # 200, 201
    assert analytics["failed_requests"] == 1  # 500
    assert analytics["total_tokens"] == 10 + 15 + 20  # 45
    assert analytics["total_cost_microcents"] == 1000 + 2000 + 3000  # 6000
    assert analytics["average_response_time_ms"] == (100 + 150 + 200) / 3

    # Check most used endpoints
    assert len(analytics["most_used_endpoints"]) >= 1
    most_used = analytics["most_used_endpoints"][0]
    assert most_used["endpoint"] == "/api/v1/test1"
    assert most_used["count"] == 2

    # Check error breakdown
    assert "500" in analytics["error_breakdown"]
    assert analytics["error_breakdown"]["500"] == 1


@pytest.mark.asyncio
async def test_get_user_summary(api_key_service, db_session: AsyncSession, test_user: dict, test_api_key):
    """Test getting comprehensive user API key summary."""
    # Record some usage
    usage_data = KeyUsageCreate(
        api_key_id=test_api_key["id"],
        user_id=test_user["id"],
        endpoint="/api/v1/test",
        method="GET",
        status_code=200,
        cost_microcents=2500,
    )

    await api_key_service.record_usage(
        api_key_id=test_api_key["id"], user_id=test_user["id"], usage_data=usage_data, db=db_session
    )

    summary = await api_key_service.get_user_summary(user_id=test_user["id"], db=db_session)

    assert summary["user_id"] == test_user["id"]
    assert summary["total_keys"] >= 1
    assert summary["active_keys"] >= 1
    assert summary["total_requests"] >= 1
    assert summary["total_cost_microcents"] >= 2500
    assert len(summary["keys"]) >= 1


@pytest.mark.asyncio
async def test_sum_user_usage_cost_not_page_capped(api_key_service, db_session: AsyncSession, test_user: dict, test_api_key):
    """Usage cost is summed in SQL, so it is not capped at a page size.

    Regression lock for the old fetch-all + Python-loop sum, which silently
    capped at FastCRUD's default 100 rows and under-reported cost for any user
    with many usage records. We seed 150 usage rows of 1_000 microcents each;
    the sum must report all 150_000, not the 100-row cap.
    """
    db_session.add_all(
        [
            KeyUsage(
                api_key_id=test_api_key["id"],
                user_id=test_user["id"],
                endpoint="/api/v1/test",
                method="GET",
                status_code=200,
                cost_microcents=1_000,
            )
            for _ in range(150)
        ]
    )
    await db_session.commit()

    total = await api_key_service.sum_user_usage_cost(user_id=test_user["id"], db=db_session)
    summary = await api_key_service.get_user_summary(user_id=test_user["id"], db=db_session)

    assert total == 150_000  # 150 * 1_000, proving no 100-row cap
    assert summary["total_requests"] == 150
    assert summary["total_cost_microcents"] == 150_000


@pytest.mark.asyncio
async def test_sum_user_usage_cost_scoped_to_user(
    api_key_service, db_session: AsyncSession, test_user: dict, test_user_2: dict, test_api_key
):
    """The sum is scoped to the given user and never bleeds another user's cost.

    Locks the ``WHERE user_id == user_id`` filter: with rows for two users, each
    user's sum reflects only their own usage.
    """
    db_session.add_all(
        [
            KeyUsage(
                api_key_id=test_api_key["id"],
                user_id=test_user["id"],
                endpoint="/api/v1/test",
                method="GET",
                status_code=200,
                cost_microcents=1_000,
            ),
            KeyUsage(
                api_key_id=test_api_key["id"],
                user_id=test_user_2["id"],
                endpoint="/api/v1/test",
                method="GET",
                status_code=200,
                cost_microcents=9_999,
            ),
        ]
    )
    await db_session.commit()

    assert await api_key_service.sum_user_usage_cost(user_id=test_user["id"], db=db_session) == 1_000
    assert await api_key_service.sum_user_usage_cost(user_id=test_user_2["id"], db=db_session) == 9_999


@pytest.mark.asyncio
async def test_get_usage_analytics_not_page_capped(api_key_service, db_session: AsyncSession, test_user: dict, test_api_key):
    """Analytics are aggregated in SQL, so no metric is truncated at 100 rows.

    Seeds 150 in-window rows (every third one a 500 on /api/v1/a, the rest 200s on
    /api/v1/b) plus one row older than the window, which must be excluded.
    """
    rows = [
        KeyUsage(
            api_key_id=test_api_key["id"],
            user_id=test_user["id"],
            endpoint="/api/v1/a" if i % 3 == 0 else "/api/v1/b",
            method="GET",
            status_code=500 if i % 3 == 0 else 200,
            tokens_used=2,
            cost_microcents=1_000,
            response_time_ms=100,
        )
        for i in range(150)
    ]
    stale = KeyUsage(
        api_key_id=test_api_key["id"],
        user_id=test_user["id"],
        endpoint="/api/v1/stale",
        method="GET",
        status_code=404,
        tokens_used=1_000,
        cost_microcents=1_000_000,
        response_time_ms=9_999,
    )
    stale.created_at = datetime.now(UTC) - timedelta(days=40)
    db_session.add_all([*rows, stale])
    await db_session.commit()

    analytics = await api_key_service.get_usage_analytics(key_id=test_api_key["id"], user_id=test_user["id"], db=db_session)

    assert analytics["total_requests"] == 150
    assert analytics["successful_requests"] == 100
    assert analytics["failed_requests"] == 50
    assert analytics["total_tokens"] == 300
    assert analytics["total_cost_microcents"] == 150_000
    assert analytics["average_response_time_ms"] == 100.0
    assert analytics["most_used_endpoints"] == [
        {"endpoint": "/api/v1/b", "count": 100},
        {"endpoint": "/api/v1/a", "count": 50},
    ]
    assert analytics["error_breakdown"] == {"500": 50}

    usage_by_day = analytics["usage_by_day"]
    assert sum(d["requests"] for d in usage_by_day) == 150
    assert sum(d["successful_requests"] for d in usage_by_day) == 100
    assert sum(d["failed_requests"] for d in usage_by_day) == 50
    assert sum(d["tokens"] for d in usage_by_day) == 300
    assert sum(d["cost_microcents"] for d in usage_by_day) == 150_000
    assert all(len(d["date"]) == 10 for d in usage_by_day)  # YYYY-MM-DD


@pytest.mark.asyncio
async def test_api_key_hash_roundtrip(api_key_service):
    """Hashing produces a fresh salt each call; verifying must still succeed."""
    test_key = "fai_test_key_12345"

    hash1 = api_key_service._hash_api_key(test_key)
    hash2 = api_key_service._hash_api_key(test_key)

    assert hash1 != hash2
    assert hash1.startswith("scrypt$")
    assert hash2.startswith("scrypt$")
    assert api_key_service._verify_api_key(test_key, hash1)
    assert api_key_service._verify_api_key(test_key, hash2)
    assert not api_key_service._verify_api_key("fai_wrong_key", hash1)


@pytest.mark.asyncio
async def test_validate_api_key_with_underscore_in_prefix(api_key_service, db_session: AsyncSession, test_user: dict):
    """Regression: secrets.token_urlsafe alphabet includes `_`; prefix extraction must not split on it.

    When the random 8-char prefix happens to contain `_`, a naive `split("_", 2)` returns the wrong
    substring and the key_prefix lookup misses, breaking validation for the (rare) keys that draw
    underscores.
    """
    api_key, prefix, key_hash = api_key_service._generate_api_key()
    forced_prefix = "ab_cd_ef"
    api_key = f"fai_{forced_prefix}_{api_key.split('_', 2)[2]}"
    forced_hash = api_key_service._hash_api_key(api_key)

    key_dict = {
        "name": "underscore prefix",
        "user_id": test_user["id"],
        "key_hash": forced_hash,
        "key_prefix": forced_prefix,
        "permissions": {},
        "usage_limits": {},
    }
    await crud_api_keys.create(db=db_session, object=APIKeyCreateInternal(**key_dict))

    permission_data = KeyPermissionCreate(
        api_key_id=(await crud_api_keys.get(db=db_session, key_prefix=forced_prefix))["id"],
        resource=KeyPermissionResource.WILDCARD,
        action=KeyPermissionAction.WILDCARD,
        is_allowed=True,
    )
    await crud_key_permissions.create(db=db_session, object=permission_data)

    validation = await api_key_service.validate_api_key(api_key=api_key, resource="anything", action="anything", db=db_session)

    assert validation.is_valid is True


@pytest.mark.asyncio
async def test_usage_pagination(api_key_service, db_session: AsyncSession, test_user: dict, test_api_key):
    """Test usage history pagination."""
    # Create multiple usage records
    for i in range(5):
        usage_data = KeyUsageCreate(
            api_key_id=test_api_key["id"], user_id=test_user["id"], endpoint=f"/api/v1/test{i}", method="GET", status_code=200
        )

        await api_key_service.record_usage(
            api_key_id=test_api_key["id"], user_id=test_user["id"], usage_data=usage_data, db=db_session
        )

    # Test pagination
    result = await api_key_service.get_key_usage(
        key_id=test_api_key["id"], user_id=test_user["id"], db=db_session, limit=3, offset=0
    )
    usage_history = result.get("data", []) if isinstance(result, dict) else []

    assert len(usage_history) == 3
