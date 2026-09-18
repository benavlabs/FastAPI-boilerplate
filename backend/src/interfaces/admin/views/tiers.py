"""Admin view for Tier model."""

from sqladmin import ModelView
from starlette.requests import Request

from ....infrastructure.database.session import local_session
from ....modules.tier.crud import crud_tiers
from ....modules.tier.models import Tier
from ....modules.tier.schemas import TierCreate, TierUpdate
from ....modules.tier.service import TierService
from ..mixins import DataclassModelMixin


class TierAdmin(DataclassModelMixin, ModelView, model=Tier):
    """Admin view for Tier model."""

    name = "Tier"
    name_plural = "Tiers"
    icon = "fa-solid fa-layer-group"
    category = "Users & Access"

    column_list = [Tier.id, Tier.name, Tier.description]
    column_details_exclude_list = [Tier.users]
    column_searchable_list = [Tier.name]
    column_sortable_list = [Tier.id, Tier.name]

    can_create = True
    can_edit = True
    can_delete = True
    can_view_details = True
    can_export = True

    form_create_rules = list(TierCreate.model_fields.keys())
    form_edit_rules = list(TierUpdate.model_fields.keys())
    form_excluded_columns = [Tier.users]

    async def delete_model(self, request: Request, pk: str) -> None:
        """Override delete to permanently remove tier from database.

        Uses the tier service's permanent_delete method which validates
        that no users or rate limits are associated before deletion.

        Args:
            request: The incoming request object.
            pk: Primary key (ID) of the tier to delete.

        Raises:
            ValueError: If tier not found or has dependencies.
        """
        async with local_session() as db:
            tier_service = TierService()

            tier = await crud_tiers.get(db=db, id=int(pk))
            if not tier:
                raise ValueError(f"Tier with ID {pk} not found")

            await tier_service.permanent_delete(tier["name"], db)
