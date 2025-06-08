"""Unit tests for user API endpoints."""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.app.api.v1.users import erase_user, patch_user, read_user, read_users, write_user
from src.app.core.exceptions.http_exceptions import DuplicateValueException, ForbiddenException, NotFoundException
from src.app.schemas.user import UserCreate, UserRead, UserUpdate


class TestWriteUser:
    """Test user creation endpoint."""

    @pytest.mark.asyncio
    async def test_create_user_success(self, mock_db, sample_user_data, sample_user_read):
        """Test successful user creation."""
        user_create = UserCreate(**sample_user_data)

        with patch("src.app.api.v1.users.crud_users") as mock_crud:
            # Mock that email and username don't exist
            mock_crud.exists = AsyncMock(side_effect=[False, False])  # email, then username
            mock_crud.create = AsyncMock(return_value=Mock(id=1))
            mock_crud.get = AsyncMock(return_value=sample_user_read)

            with patch("src.app.api.v1.users.get_password_hash") as mock_hash:
                mock_hash.return_value = "hashed_password"

                result = await write_user(Mock(), user_create, mock_db)

                assert result == sample_user_read
                mock_crud.exists.assert_any_call(db=mock_db, email=user_create.email)
                mock_crud.exists.assert_any_call(db=mock_db, username=user_create.username)
                mock_crud.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_user_duplicate_email(self, mock_db, sample_user_data):
        """Test user creation with duplicate email."""
        user_create = UserCreate(**sample_user_data)

        with patch("src.app.api.v1.users.crud_users") as mock_crud:
            # Mock that email already exists
            mock_crud.exists = AsyncMock(return_value=True)

            with pytest.raises(DuplicateValueException, match="Email is already registered"):
                await write_user(Mock(), user_create, mock_db)

    @pytest.mark.asyncio
    async def test_create_user_duplicate_username(self, mock_db, sample_user_data):
        """Test user creation with duplicate username."""
        user_create = UserCreate(**sample_user_data)

        with patch("src.app.api.v1.users.crud_users") as mock_crud:
            # Mock email doesn't exist, but username does
            mock_crud.exists = AsyncMock(side_effect=[False, True])

            with pytest.raises(DuplicateValueException, match="Username not available"):
                await write_user(Mock(), user_create, mock_db)


class TestReadUser:
    """Test user retrieval endpoint."""

    @pytest.mark.asyncio
    async def test_read_user_success(self, mock_db, sample_user_read):
        """Test successful user retrieval."""
        username = "test_user"

        with patch("src.app.api.v1.users.crud_users") as mock_crud:
            mock_crud.get = AsyncMock(return_value=sample_user_read)

            result = await read_user(Mock(), username, mock_db)

            assert result == sample_user_read
            mock_crud.get.assert_called_once_with(
                db=mock_db, username=username, is_deleted=False, schema_to_select=UserRead
            )

    @pytest.mark.asyncio
    async def test_read_user_not_found(self, mock_db):
        """Test user retrieval when user doesn't exist."""
        username = "nonexistent_user"

        with patch("src.app.api.v1.users.crud_users") as mock_crud:
            mock_crud.get = AsyncMock(return_value=None)

            with pytest.raises(NotFoundException, match="User not found"):
                await read_user(Mock(), username, mock_db)


class TestReadUsers:
    """Test users list endpoint."""

    @pytest.mark.asyncio
    async def test_read_users_success(self, mock_db):
        """Test successful users list retrieval."""
        mock_users_data = {"data": [{"id": 1}, {"id": 2}], "count": 2}

        with patch("src.app.api.v1.users.crud_users") as mock_crud:
            mock_crud.get_multi = AsyncMock(return_value=mock_users_data)

            with patch("src.app.api.v1.users.paginated_response") as mock_paginated:
                expected_response = {"data": [{"id": 1}, {"id": 2}], "pagination": {}}
                mock_paginated.return_value = expected_response

                result = await read_users(Mock(), mock_db, page=1, items_per_page=10)

                assert result == expected_response
                mock_crud.get_multi.assert_called_once()
                mock_paginated.assert_called_once()


class TestPatchUser:
    """Test user update endpoint."""

    @pytest.mark.asyncio
    async def test_patch_user_success(self, mock_db, current_user_dict, sample_user_read):
        """Test successful user update."""
        username = current_user_dict["username"]
        sample_user_read.username = username  # Make sure usernames match
        user_update = UserUpdate(name="New Name")

        with patch("src.app.api.v1.users.crud_users") as mock_crud:
            mock_crud.get = AsyncMock(return_value=sample_user_read)
            mock_crud.exists = AsyncMock(return_value=False)  # No conflicts
            mock_crud.update = AsyncMock(return_value=None)

            result = await patch_user(Mock(), user_update, username, current_user_dict, mock_db)

            assert result == {"message": "User updated"}
            mock_crud.update.assert_called_once()

    @pytest.mark.asyncio
    async def test_patch_user_forbidden(self, mock_db, current_user_dict, sample_user_read):
        """Test user update when user tries to update another user."""
        username = "different_user"
        sample_user_read.username = username
        user_update = UserUpdate(name="New Name")

        with patch("src.app.api.v1.users.crud_users") as mock_crud:
            mock_crud.get = AsyncMock(return_value=sample_user_read)

            with pytest.raises(ForbiddenException):
                await patch_user(Mock(), user_update, username, current_user_dict, mock_db)


class TestEraseUser:
    """Test user deletion endpoint."""

    @pytest.mark.asyncio
    async def test_erase_user_success(self, mock_db, current_user_dict, sample_user_read):
        """Test successful user deletion."""
        username = current_user_dict["username"]
        sample_user_read.username = username
        token = "mock_token"

        with patch("src.app.api.v1.users.crud_users") as mock_crud:
            mock_crud.get = AsyncMock(return_value=sample_user_read)
            mock_crud.delete = AsyncMock(return_value=None)

            with patch("src.app.api.v1.users.blacklist_token", new_callable=AsyncMock) as mock_blacklist:
                result = await erase_user(Mock(), username, current_user_dict, mock_db, token)

                assert result == {"message": "User deleted"}
                mock_crud.delete.assert_called_once_with(db=mock_db, username=username)
                mock_blacklist.assert_called_once_with(token=token, db=mock_db)

    @pytest.mark.asyncio
    async def test_erase_user_not_found(self, mock_db, current_user_dict):
        """Test user deletion when user doesn't exist."""
        username = "nonexistent_user"
        token = "mock_token"

        with patch("src.app.api.v1.users.crud_users") as mock_crud:
            mock_crud.get = AsyncMock(return_value=None)

            with pytest.raises(NotFoundException, match="User not found"):
                await erase_user(Mock(), username, current_user_dict, mock_db, token)

    @pytest.mark.asyncio
    async def test_erase_user_forbidden(self, mock_db, current_user_dict, sample_user_read):
        """Test user deletion when user tries to delete another user."""
        username = "different_user"
        sample_user_read.username = username
        token = "mock_token"

        with patch("src.app.api.v1.users.crud_users") as mock_crud:
            mock_crud.get = AsyncMock(return_value=sample_user_read)

            with pytest.raises(ForbiddenException):
                await erase_user(Mock(), username, current_user_dict, mock_db, token)
