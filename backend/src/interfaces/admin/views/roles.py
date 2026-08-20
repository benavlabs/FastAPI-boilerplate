"""Admin view for Role model."""

from sqladmin import ModelView
from starlette.requests import Request

from ....infrastructure.database.session import local_session
from ....modules.role.models import Role
from ....modules.role.schemas import RoleCreate, RoleUpdate
from ....modules.role.service import RoleService
from ..mixins import DataclassModelMixin


class RoleAdmin(DataclassModelMixin, ModelView, model=Role):
    """Admin view for Role model."""

    name = "Role"
    name_plural = "Roles"
    icon = "fa-solid fa-user-shield"
    category = "Users & Access"

    column_list = [Role.id, Role.name, Role.description, Role.created_at, Role.is_deleted]
    column_details_list = "__all__"
    column_searchable_list = [Role.name, Role.description]
    column_sortable_list = [Role.id, Role.name, Role.created_at]
    column_default_sort = [(Role.created_at, True)]
    column_labels = {"is_deleted": "Deleted"}

    can_create = True
    can_edit = True
    can_delete = True
    can_view_details = True
    can_export = True

    form_create_rules = list(RoleCreate.model_fields.keys())
    form_edit_rules = list(RoleUpdate.model_fields.keys())

    async def delete_model(self, request: Request, pk: str) -> None:
        """Soft-delete the role through the service layer."""
        async with local_session() as db:
            await RoleService().soft_delete(role_id=int(pk), db=db)