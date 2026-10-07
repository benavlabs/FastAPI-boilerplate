"""Admin views for the RBAC tables: roles, what they carry, and who holds them.

The panel signs in with the ``ADMIN_*`` credentials rather than as an account, and
those credentials already let it set ``is_superuser`` on any user. There is no weaker
operator to hold back here, so the API's delegation checks have nothing to compare
against: what the panel enforces instead is that a grant names a permission the
registry knows.
"""

from typing import Any, ClassVar

from sqladmin import ModelView
from sqlalchemy import select
from starlette.requests import Request
from wtforms import Form, SelectField

from ...infrastructure.permissions import permission_groups
from ...interfaces.admin.mixins import DataclassModelMixin, TextCsvExportMixin
from .models import Role, RolePermission, UserRole


def permission_choices() -> list[tuple[str, str]]:
    """Every registered permission name, as the grant form offers them."""
    return [(permission, permission) for _, permissions in sorted(permission_groups().items()) for permission in permissions]


def _user_model() -> Any:
    """The model the ``user`` relationship points at."""
    return UserRole.__mapper__.relationships["user"].mapper.class_


def _only_live_accounts(statement: Any) -> Any:
    """``statement``, narrowed to the rows whose account a soft delete hasn't taken out."""
    user_model = _user_model()

    return statement.join(user_model).filter(user_model.is_deleted.is_(False))


def carried_permissions(role: Any, _: Any) -> str:
    """The permission names a role carries, for one cell of the listing."""
    return ", ".join(sorted(grant.permission_name for grant in role.permissions))


class RoleAdmin(DataclassModelMixin, TextCsvExportMixin, ModelView, model=Role):
    """Roles, each with the permissions it carries."""

    name = "Role"
    name_plural = "Roles"
    icon = "fa-solid fa-user-shield"
    category = "Users & Access"

    column_list = [Role.id, Role.name, Role.description, Role.permissions]
    column_formatters: ClassVar[dict[Any, Any]] = {Role.permissions: carried_permissions}
    column_formatters_detail: ClassVar[dict[Any, Any]] = {Role.permissions: carried_permissions}
    column_labels = {Role.permissions: "Permissions"}
    column_searchable_list = [Role.name]
    column_sortable_list = [Role.id, Role.name]
    column_details_exclude_list = [Role.user_roles]

    can_create = True
    can_edit = True
    can_delete = True
    can_view_details = True
    can_export = True

    form_columns = [Role.name, Role.description]


class RolePermissionAdmin(DataclassModelMixin, ModelView, model=RolePermission):
    """The grants that make up a role: one permission name per row."""

    name = "Role permission"
    name_plural = "Role permissions"
    icon = "fa-solid fa-key"
    category = "Users & Access"

    column_list = [RolePermission.role, RolePermission.permission_name]
    column_labels = {RolePermission.role: "Role", RolePermission.permission_name: "Permission"}
    column_sortable_list = [RolePermission.permission_name]

    can_create = True
    can_edit = False
    can_delete = True
    can_view_details = True

    form_columns = [RolePermission.role, RolePermission.permission_name]
    form_include_pk = True
    form_overrides = {"permission_name": SelectField}

    async def scaffold_form(self, rules: list[str] | None = None) -> type[Form]:
        """The form sqladmin builds, offering only permissions the registry knows."""
        form_class = await super().scaffold_form(rules)
        form_class.permission_name.kwargs["choices"] = permission_choices()

        return form_class


class UserRoleAdmin(DataclassModelMixin, ModelView, model=UserRole):
    """Who holds which role."""

    name = "User role"
    name_plural = "User roles"
    icon = "fa-solid fa-users-gear"
    category = "Users & Access"

    column_list = [UserRole.user, UserRole.role]
    column_labels = {UserRole.user: "User", UserRole.role: "Role"}

    can_create = True
    can_edit = False
    can_delete = True
    can_view_details = True

    form_columns = [UserRole.user, UserRole.role]

    def list_query(self, request: Request) -> Any:
        """The listing, without the accounts a soft delete has already taken out."""
        return _only_live_accounts(super().list_query(request))

    def count_query(self, request: Request) -> Any:
        """The count of what the listing shows."""
        return _only_live_accounts(super().count_query(request))

    async def scaffold_form(self, rules: list[str] | None = None) -> type[Form]:
        """The form sqladmin builds, with the deleted accounts taken out of the picker."""
        form_class = await super().scaffold_form(rules)
        deleted = await self._deleted_account_keys()
        field = form_class.user
        field.kwargs["data"] = [choice for choice in field.kwargs.get("data", []) if str(choice[0]) not in deleted]

        return form_class

    async def _deleted_account_keys(self) -> set[str]:
        """The primary keys of the accounts a soft delete has taken out, as the form spells them."""
        user_model = _user_model()
        async with self.session_maker() as session:
            deleted = await session.execute(select(user_model.id).where(user_model.is_deleted.is_(True)))

        return {str(identifier) for identifier in deleted.scalars().all()}
