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


def not_nullable_columns(model: Any) -> tuple[str, ...]:
    """The names of the model's columns that cannot hold ``null``."""
    return tuple(column.key for column in model.__table__.columns if not column.nullable)


def refuse_unencodable_text(name: str, value: Any) -> None:
    """Raise when ``value`` holds text with no UTF-8 encoding, at any depth.

    Walks dicts and sequences, keys as well as values, and names the field it was
    given rather than the text it found.

    Raises:
        ValueError: Something inside ``value`` is not valid Unicode.
    """
    pending = [value]

    while pending:
        current = pending.pop()
        if isinstance(current, str):
            try:
                current.encode()
            except UnicodeEncodeError as error:
                raise ValueError(f"{name} holds text that is not valid Unicode") from error
        elif isinstance(current, dict):
            pending.extend(current.keys())
            pending.extend(current.values())
        elif isinstance(current, list | tuple | set):
            pending.extend(current)


class EncodableText(BaseModel):
    """Refuses a field holding text that has no UTF-8 encoding, at any depth.

    Checks every string field, and the keys and values inside the dicts and sequences
    they hold.
    """

    @model_validator(mode="after")
    def _text_encodes(self) -> "EncodableText":
        for name, value in self:
            refuse_unencodable_text(name, value)

        return self


def within_utc_range(value: datetime | None) -> datetime | None:
    """Return ``value`` when it still reads as a date in UTC.

    Raises:
        ValueError: The offset moves ``value`` past the dates a datetime can hold.
    """
    if value is None:
        return value

    try:
        value.astimezone(UTC)
    except (OverflowError, OSError) as error:
        raise ValueError("is too far from now to express in UTC") from error

    return value


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
