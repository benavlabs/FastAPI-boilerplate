from typing import Annotated, Literal

from pydantic import BaseModel, Field, ConfigDict


Language = Literal["zh-CN", "en-US"]
Theme = Literal["light", "dark"]


class SettingsBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    language: Annotated[Language | None, Field(examples=["zh-CN"])] = None
    theme: Annotated[Theme | None, Field(examples=["light"])] = None


class SettingsResolved(BaseModel):
    language: Language
    theme: Theme
