# Adding Models to the Admin

Adding your own models to the admin is straightforward, but there's one quirk to know upfront: the boilerplate's models use SQLAlchemy's `MappedAsDataclass`, which requires a special mixin to play nicely with SQLAdmin.

For the full range of options, see the [SQLAdmin documentation](https://github.com/smithyhq/sqladmin).

## The DataclassModelMixin

SQLAdmin's default insert flow creates an empty model instance, then sets attributes one by one. That breaks dataclass models with required fields that have no defaults.

The boilerplate solves this with `DataclassModelMixin` (`backend/src/interfaces/admin/mixins.py`) — it constructs the model with all the form data at once.

```python
from ..mixins import DataclassModelMixin

class MyModelAdmin(DataclassModelMixin, ModelView, model=MyModel):
    ...
```

**Every admin view in the codebase uses this mixin.** If you forget it, you'll get an `AttributeError` (or worse, a silent NULL) when creating records.

## Adding a New Model View

### 1. Create the View File

```python
# backend/src/interfaces/admin/views/widgets.py
from sqladmin import ModelView

from ....modules.widgets.models import Widget
from ....modules.widgets.schemas import WidgetCreate, WidgetUpdate
from ..mixins import DataclassModelMixin


class WidgetAdmin(DataclassModelMixin, ModelView, model=Widget):
    name = "Widget"
    name_plural = "Widgets"
    icon = "fa-solid fa-cube"
    category = "Inventory"

    # List view
    column_list = [Widget.id, Widget.name, Widget.owner_id, Widget.created_at]
    column_searchable_list = [Widget.name]
    column_sortable_list = [Widget.id, Widget.name, Widget.created_at]
    column_default_sort = [(Widget.id, True)]   # True = descending

    # Detail view
    column_details_list = "__all__"

    # Forms — derived from your Pydantic schemas
    form_create_rules = list(WidgetCreate.model_fields.keys())
    form_edit_rules = list(WidgetUpdate.model_fields.keys())

    # Permissions
    can_create = True
    can_edit = True
    can_delete = True
    can_view_details = True
    can_export = True
```

### 2. Register It

```python
# backend/src/interfaces/admin/views/__init__.py
from sqladmin import Admin

from .tiers import TierAdmin
from .users import UserAdmin
from .widgets import WidgetAdmin   # new

__all__ = [
    "UserAdmin",
    "TierAdmin",
    "WidgetAdmin",                  # new
    "register_admin_views",
]


def register_admin_views(admin: Admin) -> None:
    admin.add_view(UserAdmin)
    admin.add_view(TierAdmin)
    admin.add_view(WidgetAdmin)     # new
```

That's it — restart the app and Widgets show up in the sidebar under the "Inventory" category.

## Configuration Options

### Column Display

```python
column_list = [MyModel.id, MyModel.name, MyModel.status]
column_labels = {
    "hashed_password": "Password",  # rename a column header
}
```

The boilerplate's `UserAdmin` uses `column_labels` to render `hashed_password` as just "Password" — the actual hashing happens in `on_model_change`.

### Search and Sort

```python
column_searchable_list = [MyModel.name, MyModel.email]
column_sortable_list = [MyModel.id, MyModel.created_at]
column_default_sort = [(MyModel.created_at, True)]   # True = descending
```

### Form Rules

Use your Pydantic schemas to drive form fields — keeps the admin forms aligned with your API validation:

```python
form_create_rules = list(MyModelCreate.model_fields.keys())
form_edit_rules = list(MyModelUpdate.model_fields.keys())
```

You can also write the list explicitly if you want a different order or to include FK columns (more on that below).

## Foreign Keys and Relationships

The boilerplate's models use a **dual pattern**: foreign-key columns for database operations and relationships for SQLAdmin display.

### The Model Pattern

Every model that has a foreign key also defines the corresponding relationship:

```python
# modules/widgets/models.py

from typing import TYPE_CHECKING
from sqlalchemy import ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ...infrastructure.database.session import Base

if TYPE_CHECKING:
    from ..user.models import User


class Widget(Base, ...):
    __tablename__ = "widgets"
    ...

    # Foreign-key column — used by FastCRUD and DB constraints
    owner_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("user.id"), index=True,
    )

    # Relationship — used by SQLAdmin for display and form dropdowns.
    # Required: lazy="selectin" (async) and init=False (excluded from dataclass __init__)
    owner: Mapped["User"] = relationship(
        "User", lazy="selectin", init=False,
    )
```

### Why Both?

- **FastCRUD** works with FK columns directly and returns dicts: `widget["owner_id"]`
- **SQLAdmin** uses the relationship to render a friendly dropdown showing the related object's `__repr__` instead of a raw integer

### `column_list` Uses the Relationship

```python
class WidgetAdmin(DataclassModelMixin, ModelView, model=Widget):
    # Use Widget.owner (relationship), not Widget.owner_id (FK column).
    # This shows "user@example.com" instead of just an integer.
    column_list = [Widget.id, Widget.name, Widget.owner, Widget.created_at]
```

The boilerplate's `UserAdmin` does this for tier:

```python
column_list = [User.id, User.name, User.username, User.email, User.is_superuser, User.tier]
```

`User.tier` is the relationship, not `User.tier_id`.

### Form Rules Use FK Column Names

For forms, include the **FK column name** (the underscore-id one) in your rules. SQLAdmin auto-generates a searchable dropdown:

```python
form_create_rules = [*WidgetCreate.model_fields.keys(), "owner_id"]
```

### `lazy="selectin"` Is Required

SQLAdmin runs in async context, so relationships must use `lazy="selectin"` to avoid lazy-loading errors. Symptom of forgetting: `MissingGreenlet` or `greenlet_spawn has not been called`. Both User and Tier models in the boilerplate already use this pattern.

### Don't Set `default=None` on Relationships

For nullable foreign keys, never set `default=None` on the relationship:

```python
# WRONG — SQLAlchemy clears the FK during commit
tier: Mapped["Tier | None"] = relationship("Tier", default=None, init=False)

# CORRECT — relationship returns None naturally when FK is null
tier: Mapped["Tier | None"] = relationship("Tier", init=False)
```

The User model demonstrates the correct pattern.

`DataclassModelMixin` automatically filters out relationship objects before constructing the dataclass — so the form data containing `owner_id=42` works, but a stray `owner=<User instance>` would be ignored.

## Data Transformation Hooks

### `on_model_change` — Transform Before Save

Runs before insert and update. Use it to hash passwords, normalize fields, etc.

```python
from typing import Any
from starlette.requests import Request


class UserAdmin(DataclassModelMixin, ModelView, model=User):
    async def on_model_change(
        self,
        data: dict[str, Any],
        model: Any,
        is_created: bool,
        request: Request,
    ) -> None:
        if is_created and data.get("hashed_password"):
            # Form's "Password" field maps to hashed_password column;
            # hash the plaintext before the row is created
            data["hashed_password"] = get_password_hash(data["hashed_password"])
```

`is_created` distinguishes create from update. For new records, `model` is `None`.

### `after_model_change` — Side Effects After Save

Runs after the record is committed. Useful for sending welcome emails, dispatching webhooks, etc.

```python
async def after_model_change(
    self,
    data: dict[str, Any],
    model: Any,
    is_created: bool,
    request: Request,
) -> None:
    if is_created:
        await notify_new_user(model)
```

### `delete_model` — Custom Delete Behavior

Override when delete needs to do more than `DELETE FROM`. The boilerplate's `TierAdmin` uses this to call the tier service's `permanent_delete`, which validates that no users or rate limits still reference the tier:

```python
async def delete_model(self, request: Request, pk: str) -> None:
    from ....modules.tier.crud import crud_tiers

    async with local_session() as db:
        tier_service = TierService()

        tier = await crud_tiers.get(db=db, id=int(pk))
        if not tier:
            raise ValueError(f"Tier with ID {pk} not found")

        await tier_service.permanent_delete(tier["name"], db)
```

## Bulk Actions

Bulk actions let admins select multiple records and operate on them at once. Use the `@action` decorator:

```python
from sqladmin import action
from starlette.requests import Request
from starlette.responses import RedirectResponse


class WidgetAdmin(DataclassModelMixin, ModelView, model=Widget):
    @action(
        name="deactivate",
        label="Deactivate Selected",
        confirmation_message="Deactivate these widgets?",
        add_in_list=True,
    )
    async def action_deactivate(self, request: Request) -> RedirectResponse:
        pks = request.query_params.get("pks", "").split(",")
        if pks and pks[0]:
            ids = [int(pk) for pk in pks]
            async with local_session() as db:
                await crud_widgets.update(
                    db=db,
                    object={"is_active": False},
                    allow_multiple=True,
                    id__in=ids,
                )
                await db.commit()

        referer = request.headers.get("Referer")
        return RedirectResponse(referer or request.url_for("admin:list", identity=self.identity))
```

Notes:

- Selected IDs come from `request.query_params["pks"]` as a comma-separated string
- `local_session()` is the boilerplate's session-maker — import it from `infrastructure/database/session.py`
- Always commit before redirecting, otherwise the change reverts when the request ends

## Icons

SQLAdmin uses [Font Awesome](https://fontawesome.com/icons) icons. Set them with `icon`:

```python
icon = "fa-solid fa-user"          # users
icon = "fa-solid fa-layer-group"   # tiers / categories
icon = "fa-solid fa-key"           # api keys
icon = "fa-solid fa-gauge-high"    # rate limits
icon = "fa-solid fa-cube"          # generic
```

## Categories

Group related views together with `category`:

```python
class WidgetAdmin(...):
    category = "Inventory"
```

Views with the same category appear under the same sidebar header. The boilerplate's existing views use `"Users & Access"`.

## Soft Delete vs Hard Delete

Models that mix in `SoftDeleteMixin` have `is_deleted` and `deleted_at` columns. SQLAdmin's default delete is a hard `DELETE FROM` — if you want soft-deletion behavior, override `delete_model`:

```python
async def delete_model(self, request: Request, pk: str) -> None:
    async with local_session() as db:
        await crud_widgets.delete(db=db, id=int(pk))   # FastCRUD soft-deletes via the mixin
        await db.commit()
```

Most of the time you actually want a hard delete here (the admin is editing the canonical row, not making a user-visible deletion), but be deliberate about which behavior you want.

## Real Examples in the Codebase

The boilerplate ships two admin views — read them as reference implementations:

| File | What it shows |
|------|---------------|
| `backend/src/interfaces/admin/views/users.py` | `on_model_change` for password hashing, OAuth-provider select field, relationship in `column_list`, custom `column_labels` |
| `backend/src/interfaces/admin/views/tiers.py` | `delete_model` override that calls a service method, schema-driven form rules |

## Key Files

| Component | Location |
|-----------|----------|
| Dataclass mixin | `backend/src/interfaces/admin/mixins.py` |
| View registry | `backend/src/interfaces/admin/views/__init__.py` |
| Example views | `backend/src/interfaces/admin/views/*.py` |
| Auth backend | `backend/src/interfaces/admin/auth.py` |

## Next Steps

- **[User Management](user-management.md)** — Hardening admin authentication
- **[Models](../database/models.md)** — Defining the SQLAlchemy models that admin views render
- **[Schemas](../database/schemas.md)** — Pydantic schemas used for form rules
