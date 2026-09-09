"""Tests for database resource teardown."""

from unittest.mock import AsyncMock, patch

import pytest

from src.infrastructure.database.initialize import close_database

pytestmark = pytest.mark.asyncio


class TestCloseDatabase:
    """Test cases for close_database."""

    async def test_disposes_the_engine(self):
        """close_database disposes the module-level engine."""
        with patch("src.infrastructure.database.initialize.engine") as mock_engine:
            mock_engine.dispose = AsyncMock()

            await close_database()

            mock_engine.dispose.assert_awaited_once()

    async def test_is_safe_to_call_twice(self):
        """Disposing an already disposed engine does not raise."""
        with patch("src.infrastructure.database.initialize.engine") as mock_engine:
            mock_engine.dispose = AsyncMock()

            await close_database()
            await close_database()

            assert mock_engine.dispose.await_count == 2
