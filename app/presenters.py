"""Serialize ORM objects into plain dicts for templates and embedded JSON.

Used by:
* the review/edit screen (client JS rebuilds editable rows from this structure), and
* the detail view (client JS scales/converts quantities from this structure).
"""
from __future__ import annotations

from app.models import Ingredient, Recipe


def ingredient_to_dict(ing: Ingredient) -> dict:
    return {
        "raw_text": ing.raw_text,
        "quantity": ing.quantity,
        "quantity_max": ing.quantity_max,
        "unit": ing.unit,
        "name": ing.name,
        "note": ing.note,
        "parsed": bool(ing.parsed),
    }


def recipe_to_review_dict(recipe: Recipe) -> dict:
    """Structure matching what the scraper produces, for the review/edit form."""
    return {
        "title": recipe.title,
        "source_url": recipe.source_url,
        "image_url": recipe.image_url,
        "servings": recipe.servings,
        "prep_time": recipe.prep_time,
        "cook_time": recipe.cook_time,
        "total_time": recipe.total_time,
        "instructions": list(recipe.instructions or []),
        "tags": [t.name for t in recipe.tags],
        "groups": [
            {
                "title": g.title,
                "ingredients": [ingredient_to_dict(i) for i in g.ingredients],
            }
            for g in recipe.groups
        ],
    }


def recipe_to_detail_dict(recipe: Recipe) -> dict:
    """Structure the detail page embeds for client-side scaling and unit toggle."""
    return {
        "id": recipe.id,
        "servings": recipe.servings,
        "groups": [
            {
                "title": g.title,
                "ingredients": [ingredient_to_dict(i) for i in g.ingredients],
            }
            for g in recipe.groups
        ],
        "instructions": list(recipe.instructions or []),
    }


def scraped_to_review_dict(scraped: dict) -> dict:
    """Normalize a scraper result into the review-form structure (adds empty tags)."""
    data = dict(scraped)
    data.setdefault("tags", [])
    return data
