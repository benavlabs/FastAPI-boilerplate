"""Admin view for role ↔ permission assignments."""

from sqladmin import ModelView
from wtforms import SelectField

from ....modules.role.models import RolePermission
from ....modules.role.permissions import permission_choices
from ..mixins import DataclassModelMixin


class RolePermissionAdmin(DataclassModelMixin, ModelView, model=RolePermission):
    """Assign permission-tree names to roles."""

    name = "Role Permission"
    name_plural = "Role Permissions"
    icon = "fa-solid fa-key"
    category = "Users & Access"

    column_list = [
        RolePermission.id,
        RolePermission.role,
        RolePermission.permission_name,
        RolePermission.created_at,
    ]
    column_labels = {"role": "Role", "permission_name": "Permission"}
    column_searchable_list = [RolePermission.permission_name]
    column_sortable_list = [RolePermission.id, RolePermission.permission_name]
    column_default_sort = [(RolePermission.id, True)]

    form_columns = [RolePermission.role_id, RolePermission.permission_name]
    form_overrides = {"permission_name": SelectField}
    form_args = {"permission_name": {"choices": permission_choices()}}

    can_create = True
    can_edit = True
    can_delete = True
    can_view_details = True
    can_export = True