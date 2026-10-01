"""Admin view for the User model.

The tier column and form field appear only when the tiers feature contributed
them to the model.
"""

from typing import Any

from crudauth import get_password_hash_async
from crudauth.utils import canonical_email
from sqladmin import ModelView
from starlette.requests import Request
from wtforms import SelectField

from ...infrastructure.auth.setup import auth
from ...infrastructure.database.session import local_session
from ...interfaces.admin.mixins import DataclassModelMixin, TextCsvExportMixin
from .enums import OAuthProvider
from .models import User
from .schemas import UserAdminUpdate
from .service import UserService

OAUTH_PROVIDER_CHOICES = [("", "None")] + [(p.value, p.value.title()) for p in OAuthProvider]


class UserAdmin(DataclassModelMixin, TextCsvExportMixin, ModelView, model=User):
    """Admin view for User model with password hashing."""

    name = "User"
    name_plural = "Users"
    icon = "fa-solid fa-user"
    category = "Users & Access"

    column_list = [User.id, User.name, User.username, User.email, User.is_superuser]
    if hasattr(User, "tier"):
        column_list = [*column_list, User.tier]
    column_details_exclude_list = [User.hashed_password]
    column_searchable_list = [User.name, User.username, User.email]
    column_sortable_list = [User.id, User.name, User.username, User.email]
    column_default_sort = [(User.id, True)]

    can_create = True
    can_edit = True
    can_delete = True
    can_view_details = True
    can_export = True

    column_labels = {"hashed_password": "Password"}

    _tier_rules = ["tier"] if hasattr(User, "tier") else []
    form_create_rules = ["name", "username", "email", "hashed_password", *_tier_rules, "is_superuser"]
    form_edit_rules = [*UserAdminUpdate.model_fields.keys(), *_tier_rules, "is_superuser"]

    form_overrides = {"oauth_provider": SelectField}
    form_args = {"oauth_provider": {"choices": OAUTH_PROVIDER_CHOICES}}

    async def on_model_change(self, data: dict[str, Any], model: Any, is_created: bool, request: Request) -> None:
        """Hash the password and canonicalise the address before saving.

        A row written here is signed in to through crudauth, which looks accounts
        up by the canonical address.
        """
        if is_created and "hashed_password" in data and data["hashed_password"]:
            await auth.validate_password(data["hashed_password"])
            data["hashed_password"] = await get_password_hash_async(data["hashed_password"])
        if data.get("email"):
            data["email"] = canonical_email(data["email"])
            if not is_created and data["email"] != canonical_email(model.email):
                data["email_verified"] = False
        if "oauth_provider" in data and data["oauth_provider"] == "":
            data["oauth_provider"] = None
        if data.get("tier") is not None and getattr(data["tier"], "is_deleted", False):
            raise ValueError("That tier has been deleted. Pick another one, or restore it first.")

    async def delete_model(self, request: Request, pk: str) -> None:
        """Override delete to anonymize user instead of removing.

        GDPR/LGPD compliant deletion that:
        - Anonymizes all PII (name, username, password, OAuth data)
        - Retains email and timestamps for legal compliance
        - Soft deletes the user (is_deleted = True)
        - Maintains foreign key relationships

        Args:
            request: The incoming request object.
            pk: Primary key (ID) of the user to anonymize.
        """
        async with local_session() as db:
            user_service = UserService()
            await user_service.anonymize_user(user_id=int(pk), db=db)
