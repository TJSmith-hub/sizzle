"""Pydantic schemas.

The review/edit screen serializes the whole recipe structure to a single JSON
payload (built client-side) and posts it in one hidden form field. These schemas
validate and normalize that payload before it is written to the database.
"""
from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class IngredientIn(BaseModel):
    raw_text: str = Field(..., min_length=1)
    quantity: float | None = None
    quantity_max: float | None = None
    unit: str | None = None
    name: str | None = None
    note: str | None = None
    parsed: bool = False

    @field_validator("unit", "name", "note", mode="before")
    @classmethod
    def _empty_to_none(cls, v):
        if isinstance(v, str) and v.strip() == "":
            return None
        return v

    @field_validator("raw_text", mode="before")
    @classmethod
    def _strip_raw(cls, v):
        return v.strip() if isinstance(v, str) else v


class GroupIn(BaseModel):
    # Empty / whitespace-only title means the default (ungrouped) section.
    title: str | None = None
    ingredients: list[IngredientIn] = Field(default_factory=list)

    @field_validator("title", mode="before")
    @classmethod
    def _blank_title_to_none(cls, v):
        if isinstance(v, str) and v.strip() == "":
            return None
        return v.strip() if isinstance(v, str) else v


class RecipeIn(BaseModel):
    title: str = Field(..., min_length=1)
    source_url: str | None = None
    image_url: str | None = None
    servings: int | None = Field(default=None, ge=1)
    prep_time: int | None = Field(default=None, ge=0)
    cook_time: int | None = Field(default=None, ge=0)
    total_time: int | None = Field(default=None, ge=0)
    instructions: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    groups: list[GroupIn] = Field(default_factory=list)

    @field_validator("title", mode="before")
    @classmethod
    def _strip_title(cls, v):
        return v.strip() if isinstance(v, str) else v

    @field_validator("instructions", mode="before")
    @classmethod
    def _clean_instructions(cls, v):
        if not isinstance(v, list):
            return []
        return [s.strip() for s in v if isinstance(s, str) and s.strip()]

    @field_validator("tags", mode="before")
    @classmethod
    def _clean_tags(cls, v):
        if isinstance(v, str):
            v = v.split(",")
        if not isinstance(v, list):
            return []
        seen: set[str] = set()
        out: list[str] = []
        for raw in v:
            if not isinstance(raw, str):
                continue
            tag = raw.strip().lower()
            if tag and tag not in seen:
                seen.add(tag)
                out.append(tag)
        return out
