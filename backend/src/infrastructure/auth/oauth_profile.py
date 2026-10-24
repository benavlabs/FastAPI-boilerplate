"""What an OAuth sign-in writes back onto the account it signed in.

Registered as crudauth's ``on_oauth_login`` hook, which runs on every OAuth sign-in that
reaches an active account: the one that created it, one that linked it by email, and every
later one found by provider id.

``oauth_updated_at`` is stamped on each of those but the sign-in that created the account,
where crudauth has just written it. The provider's picture is taken while the account still
carries the placeholder avatar it was created with, so an account that set one of its own
keeps it. Its display name is its own from the moment it exists: crudauth seeds that from
the provider once, through ``new_user_fields``.

The hook is handed crudauth's logical fields alone, so the avatar is read from the row.
"""

from datetime import UTC, datetime
from typing import Any

from crudauth import HookContext
from crudauth.oauth import OAuthUserInfo
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ...modules.user.constants import DEFAULT_PROFILE_IMAGE_URL, PROFILE_IMAGE_URL_MAX_LENGTH
from ...modules.user.crud import crud_users


class AvatarRead(BaseModel):
    """The one column this hook reads back."""

    profile_image_url: str


async def _carries_the_placeholder_avatar(user_id: int, db: AsyncSession) -> bool:
    """Whether the account still has the avatar it was created with."""
    stored = await crud_users.get(db=db, id=user_id, schema_to_select=AvatarRead)

    return stored is not None and stored["profile_image_url"] == DEFAULT_PROFILE_IMAGE_URL


async def refresh_the_provider_profile(
    user: dict[str, Any],
    info: OAuthUserInfo,
    *,
    db: AsyncSession,
    created: bool,
    context: HookContext,
) -> None:
    """Write what the provider owns onto the account that just signed in with it.

    A picture longer than the column's own callers may send is left out: the URL is served
    to everybody who reads the profile.
    """
    changes: dict[str, Any] = {} if created else {"oauth_updated_at": datetime.now(UTC)}
    pictured = info.picture and len(info.picture) <= PROFILE_IMAGE_URL_MAX_LENGTH
    if pictured and await _carries_the_placeholder_avatar(user["id"], db):
        changes["profile_image_url"] = info.picture

    if not changes:
        return

    await crud_users.update(db=db, object=changes, id=user["id"])
