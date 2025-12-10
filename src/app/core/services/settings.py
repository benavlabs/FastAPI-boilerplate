from __future__ import annotations

from typing import Any, Literal, cast

from pydantic import ValidationError
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ...models.setting import Setting
from ...schemas.setting import SettingsBase, SettingsResolved


ALLOWED_KEYS = set(SettingsBase.model_fields.keys())
DEFAULTS = {"language": "zh-CN", "theme": "light"}
Scope = Literal["user", "app"]


class SettingsManager:
    async def _get_row(self, db: AsyncSession, scope: Scope, user_id: Any | None) -> Setting | None:
        stmt = select(Setting).where(Setting.scope == scope)
        if scope == "user":
            stmt = stmt.where(Setting.user_id == user_id)
        else:
            stmt = stmt.where(Setting.user_id.is_(None))
        res = await db.execute(stmt)
        return res.scalar_one_or_none()

    async def _ensure_row(self, db: AsyncSession, scope: Scope, user_id: Any | None) -> Setting:
        row = await self._get_row(db, scope, user_id)
        if row is not None:
            return row
        new = Setting(scope=scope)
        new.user_id = user_id
        new.data = {}
        db.add(new)
        await db.commit()
        await db.refresh(new)
        return new

    def _validate_patch(self, patch: dict[str, Any]) -> dict[str, Any]:
        _ = SettingsBase(**patch)
        return patch

    async def get(self, key: str, db: AsyncSession, *, scope: Scope | None = None, user_id: Any | None = None, default: Any | None = None) -> Any:
        if key not in ALLOWED_KEYS:
            raise ValueError("invalid key")
        if scope == "user" and user_id is None:
            scope = "app"
        if scope is None:
            scope = "user" if user_id is not None else "app"
        user_val: Any | None = None
        app_val: Any | None = None
        if scope == "user":
            row_user = await self._get_row(db, "user", user_id)
            if row_user and isinstance(row_user.data, dict):
                user_val = row_user.data.get(key)
        row_app = await self._get_row(db, "app", None)
        if row_app and isinstance(row_app.data, dict):
            app_val = row_app.data.get(key)
        if user_val is not None:
            return user_val
        if app_val is not None:
            return app_val
        return default if default is not None else DEFAULTS.get(key)

    async def get_all(self, db: AsyncSession, *, user_id: Any | None = None) -> dict[str, Any]:
        base = dict(DEFAULTS)
        row_app = await self._get_row(db, "app", None)
        app_data = row_app.data if row_app and isinstance(row_app.data, dict) else {}
        try:
            app_valid = SettingsBase(**app_data).model_dump(exclude_none=True)
        except ValidationError:
            app_valid = {}
        base.update(app_valid)
        if user_id is not None:
            row_user = await self._get_row(db, "user", user_id)
            user_data = row_user.data if row_user and isinstance(row_user.data, dict) else {}
            try:
                user_valid = SettingsBase(**user_data).model_dump(exclude_none=True)
            except ValidationError:
                user_valid = {}
            base.update(user_valid)
        language = cast(Literal["zh-CN", "en-US"], base["language"])  # type: ignore[arg-type]
        theme = cast(Literal["light", "dark"], base["theme"])  # type: ignore[arg-type]
        resolved = SettingsResolved(language=language, theme=theme)
        return resolved.model_dump()

    async def set(self, key: str, value: Any, db: AsyncSession, *, scope: Scope, user_id: Any | None = None) -> None:
        if scope not in {"user", "app"}:
            raise ValueError("invalid scope")
        if scope == "user" and user_id is None:
            raise ValueError("user_id required for user scope")
        if key not in ALLOWED_KEYS:
            raise ValueError("invalid key")
        patch = {key: value}
        self._validate_patch(patch)
        row = await self._ensure_row(db, scope, user_id)
        data = dict(row.data or {})
        data.update(patch)
        stmt = update(Setting).where(Setting.id == row.id).values(data=data)
        await db.execute(stmt)
        await db.commit()

    async def update(self, patch: dict[str, Any], db: AsyncSession, *, scope: Scope, user_id: Any | None = None) -> None:
        if scope not in {"user", "app"}:
            raise ValueError("invalid scope")
        if scope == "user" and user_id is None:
            raise ValueError("user_id required for user scope")
        self._validate_patch(patch)
        row = await self._ensure_row(db, scope, user_id)
        data = dict(row.data or {})
        data.update(patch)
        stmt = update(Setting).where(Setting.id == row.id).values(data=data)
        await db.execute(stmt)
        await db.commit()

    async def remove(self, key: str, db: AsyncSession, *, scope: Scope, user_id: Any | None = None) -> None:
        if scope not in {"user", "app"}:
            raise ValueError("invalid scope")
        if scope == "user" and user_id is None:
            raise ValueError("user_id required for user scope")
        if key not in ALLOWED_KEYS:
            raise ValueError("invalid key")
        row = await self._get_row(db, scope, user_id)
        if row is None:
            return
        data = dict(row.data or {})
        if key in data:
            data.pop(key)
            stmt = update(Setting).where(Setting.id == row.id).values(data=data)
            await db.execute(stmt)
            await db.commit()


settings_manager = SettingsManager()
