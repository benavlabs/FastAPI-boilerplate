from datetime import UTC, datetime
from typing import Any, ClassVar

from pydantic import BaseModel, Field, field_serializer, model_validator


class TimestampSchema(BaseModel):
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC).replace(tzinfo=None))
    updated_at: datetime | None = Field(default=None)

    @field_serializer("created_at")
    def serialize_dt(self, created_at: datetime | None, _info: Any) -> str | None:
        if created_at is not None:
            return created_at.isoformat()

        return None

    @field_serializer("updated_at")
    def serialize_updated_at(self, updated_at: datetime | None, _info: Any) -> str | None:
        if updated_at is not None:
            return updated_at.isoformat()

        return None


class PersistentDeletion(BaseModel):
    deleted_at: datetime | None = Field(default=None)
    is_deleted: bool = False

    @field_serializer("deleted_at")
    def serialize_dates(self, deleted_at: datetime | None, _info: Any) -> str | None:
        if deleted_at is not None:
            return deleted_at.isoformat()

        return None


class PartialUpdate(BaseModel):
    """A partial update: omit a field to leave it alone.

    ``null`` is a value, not an omission, and the columns named in
    ``NOT_NULLABLE`` cannot hold it. Refusing it here answers 422 instead of
    letting the database refuse the write as a server error.
    """

    NOT_NULLABLE: ClassVar[tuple[str, ...]] = ()

    @model_validator(mode="before")
    @classmethod
    def _refuse_explicit_nulls(cls, data: Any) -> Any:
        if isinstance(data, dict):
            nulled = sorted(name for name in cls.NOT_NULLABLE if name in data and data[name] is None)
            if nulled:
                raise ValueError(f"These fields cannot be set to null: {', '.join(nulled)}")

        return data
