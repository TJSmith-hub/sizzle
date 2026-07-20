"""Database helpers for creating/updating recipes from validated payloads."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Ingredient, IngredientGroup, Recipe, Tag
from app.schemas import RecipeIn


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
