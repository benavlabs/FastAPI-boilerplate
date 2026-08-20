"""Admin view for user ↔ role assignments."""

from sqladmin import ModelView

from ....modules.role.models import UserRole
from ..mixins import DataclassModelMixin


class UserRoleAdmin(DataclassModelMixin, ModelView, model=UserRole):
    """Assign roles to users."""

    name = "User Role"
    name_plural = "User Roles"
    icon = "fa-solid fa-link"
    category = "Users & Access"

    column_list = [UserRole.id, UserRole.user, UserRole.role, UserRole.created_at]
    column_labels = {"user": "User", "role": "Role"}
    column_sortable_list = [UserRole.created_at]
    column_default_sort = [(UserRole.created_at, True)]
    form_columns = [UserRole.user_id, UserRole.role_id]

    can_create = True
    can_edit = True
    can_delete = True
    can_view_details = True
    can_export = True