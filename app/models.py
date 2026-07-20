"""SQLAlchemy ORM models.

Data model notes
----------------
The whole point of this app is that ingredients are stored as *structured* data
(quantity + unit + name) inside *named groups*, not as a flat list of strings.
That structure is what makes scaling, unit conversion, and cross-recipe shopping
list merging possible.

Relationships / cascades are set up so that deleting a Recipe removes its groups
and ingredients, and deleting a group removes its ingredients.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# Many-to-many association between recipes and tags.
recipe_tags = Table(
    "recipe_tags",
    Base.metadata,
    Column("recipe_id", ForeignKey("recipes.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
)


class Tag(Base):
    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)

    recipes: Mapped[list["Recipe"]] = relationship(
        secondary=recipe_tags, back_populates="tags"
    )


class Recipe(Base):
    __tablename__ = "recipes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    source_url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    image_url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)

    # Base servings used as the reference point for scaling. Nullable if unknown.
    servings: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Times stored as integer minutes (nullable when the source doesn't provide them).
    prep_time: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    cook_time: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    total_time: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Ordered list of instruction step strings.
    instructions: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)

    # Optional per-recipe unit-system override ("metric"/"imperial"); when null the
    # global DEFAULT_UNIT_SYSTEM applies. The live UI toggle also persists to the
    # browser's localStorage, so this column is a convenience, not a hard dependency.
    preferred_system: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, onupdate=_utcnow, nullable=False
    )

    tags: Mapped[list[Tag]] = relationship(
        secondary=recipe_tags, back_populates="recipes", lazy="selectin"
    )
    groups: Mapped[list["IngredientGroup"]] = relationship(
        back_populates="recipe",
        cascade="all, delete-orphan",
        order_by="IngredientGroup.position",
        lazy="selectin",
    )


class IngredientGroup(Base):
    __tablename__ = "ingredient_groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    recipe_id: Mapped[int] = mapped_column(
        ForeignKey("recipes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Null title == the default/ungrouped section (rendered without a heading).
    title: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    recipe: Mapped[Recipe] = relationship(back_populates="groups")
    ingredients: Mapped[list["Ingredient"]] = relationship(
        back_populates="group",
        cascade="all, delete-orphan",
        order_by="Ingredient.position",
        lazy="selectin",
    )


class Ingredient(Base):
    __tablename__ = "ingredients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    group_id: Mapped[int] = mapped_column(
        ForeignKey("ingredient_groups.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Original scraped/entered text. Always authoritative — displayed verbatim as a
    # fallback whenever parsing failed (parsed == False).
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)

    # Structured fields. quantity/unit/name are null when parsing failed.
    quantity: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    quantity_max: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # range high end
    unit: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    name: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    # Trailing preparation note split off from the name ("finely chopped").
    note: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)

    # True when a numeric quantity was successfully parsed (so it can be scaled).
    parsed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    group: Mapped[IngredientGroup] = relationship(back_populates="ingredients")


class ShoppingListItem(Base):
    """A single persistent shopping-list line item.

    There is one running list (single-user app), stored as discrete rows rather
    than merged/summed across recipes -- that keeps every row independently
    editable and deletable instead of tangling checkbox/edit state across a
    merged quantity. ``source`` is a denormalized snapshot of the recipe title
    it came from (or None for a manually-added item), so the list still reads
    sensibly even if that recipe is later edited or deleted.
    """

    __tablename__ = "shopping_list_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    quantity: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    quantity_max: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    unit: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    note: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    source: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    checked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)
