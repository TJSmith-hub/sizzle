"""Database helpers for creating/updating recipes from validated payloads."""
from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Ingredient, IngredientGroup, Recipe, ShoppingListItem, Tag
from app.schemas import RecipeIn
from app.services import units
from app.services.shopping_list import normalize_name


def _get_or_create_tags(db: Session, names: list[str]) -> list[Tag]:
    tags: list[Tag] = []
    for name in names:
        tag = db.scalar(select(Tag).where(Tag.name == name))
        if tag is None:
            tag = Tag(name=name)
            db.add(tag)
        tags.append(tag)
    return tags


def _apply_groups(recipe: Recipe, data: RecipeIn) -> None:
    """Replace a recipe's groups/ingredients with those from the payload."""
    recipe.groups.clear()  # delete-orphan cascade removes old rows on flush
    for g_pos, group in enumerate(data.groups):
        # Skip entirely empty groups (no title and no ingredients).
        if group.title is None and not group.ingredients:
            continue
        db_group = IngredientGroup(title=group.title, position=g_pos)
        for i_pos, ing in enumerate(group.ingredients):
            db_group.ingredients.append(
                Ingredient(
                    raw_text=ing.raw_text,
                    quantity=ing.quantity,
                    quantity_max=ing.quantity_max,
                    unit=ing.unit,
                    name=ing.name,
                    note=ing.note,
                    parsed=bool(ing.parsed and ing.quantity is not None),
                    position=i_pos,
                )
            )
        recipe.groups.append(db_group)


def create_recipe(db: Session, data: RecipeIn) -> Recipe:
    recipe = Recipe(
        title=data.title,
        source_url=data.source_url,
        image_url=data.image_url,
        servings=data.servings,
        prep_time=data.prep_time,
        cook_time=data.cook_time,
        total_time=data.total_time,
        instructions=data.instructions,
    )
    recipe.tags = _get_or_create_tags(db, data.tags)
    _apply_groups(recipe, data)
    db.add(recipe)
    db.commit()
    db.refresh(recipe)
    return recipe


def update_recipe(db: Session, recipe: Recipe, data: RecipeIn) -> Recipe:
    recipe.title = data.title
    recipe.source_url = data.source_url
    recipe.image_url = data.image_url
    recipe.servings = data.servings
    recipe.prep_time = data.prep_time
    recipe.cook_time = data.cook_time
    recipe.total_time = data.total_time
    recipe.instructions = data.instructions
    recipe.tags = _get_or_create_tags(db, data.tags)
    _apply_groups(recipe, data)
    db.commit()
    db.refresh(recipe)
    return recipe


def add_shopping_item(
    db: Session,
    *,
    name: str,
    quantity: Optional[float] = None,
    quantity_max: Optional[float] = None,
    unit: Optional[str] = None,
    note: Optional[str] = None,
    source: Optional[str] = None,
) -> ShoppingListItem:
    """Add a line to the shopping list, combining it into a matching unchecked
    row when possible instead of always creating a new one.

    Two rows combine when they normalize to the same ingredient name (see
    ``normalize_name``) and have compatible units (same measurement type, e.g.
    both volume) -- the new quantity is summed into the existing row, converted
    into whatever unit that row already uses. Rows with no numeric quantity
    (unparsed ingredients, or a plain "salt to taste") are never merged, since
    there's nothing to sum. Checked-off rows are left alone -- merging into
    something already marked "bought" would silently un-tick it.
    """
    norm = normalize_name(name)
    if quantity is not None and norm:
        mtype = units.measurement_type(unit)
        candidates = db.scalars(
            select(ShoppingListItem).where(ShoppingListItem.checked.is_(False))
        )
        for existing in candidates:
            if existing.quantity is None:
                continue
            if normalize_name(existing.name) != norm:
                continue
            if units.measurement_type(existing.unit) != mtype:
                continue
            add_qty = units.convert(quantity, unit, existing.unit)
            if add_qty is None:
                continue
            existing_val = existing.quantity
            if existing.quantity_max is not None:
                existing_val = existing.quantity_max
                existing.quantity_max = None
            if quantity_max is not None:
                converted_max = units.convert(quantity_max, unit, existing.unit)
                if converted_max is not None:
                    add_qty = converted_max
            existing.quantity = existing_val + add_qty
            if not existing.note and note:
                existing.note = note
            if source and source not in (existing.source or ""):
                existing.source = f"{existing.source}, {source}" if existing.source else source
            db.commit()
            return existing

    item = ShoppingListItem(
        name=name, quantity=quantity, quantity_max=quantity_max,
        unit=unit, note=note, source=source,
    )
    db.add(item)
    db.commit()
    return item


def add_recipe_to_shopping_list(db: Session, recipe: Recipe) -> int:
    """Add every ingredient of ``recipe`` to the shopping list, combining
    duplicates into existing unchecked rows where possible. Returns the number
    of ingredient lines processed."""
    count = 0
    for group in recipe.groups:
        for ing in group.ingredients:
            name = (ing.name or ing.raw_text or "").strip()
            if not name:
                continue
            add_shopping_item(
                db,
                name=name,
                quantity=ing.quantity if ing.parsed else None,
                quantity_max=ing.quantity_max if ing.parsed else None,
                unit=ing.unit if ing.parsed else None,
                # Prep notes ("finely chopped") describe cooking, not buying --
                # left out of the shopping list. Manually-added items can still
                # carry their own note (e.g. "get the organic one").
                note=None,
                source=recipe.title,
            )
            count += 1
    return count
