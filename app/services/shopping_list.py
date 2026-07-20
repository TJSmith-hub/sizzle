"""Build a combined, aisle-grouped shopping list from several recipes.

Steps:
1. Flatten every ingredient across the selected recipes.
2. Merge duplicates: ingredients with the same normalized name AND compatible
   units (same measurement type) are converted to a common unit and summed.
   Incompatible units or unparsed lines are kept as separate entries -- never
   guessed.
3. Convert each merged quantity into the user's preferred unit system.
4. Categorize each item into a grocery aisle and order aisles for printing.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from app.models import Recipe
from app.services import units
from app.services.aisles import AISLE_ORDER, categorize


@dataclass
class ShoppingItem:
    name: str
    quantity: Optional[float]  # None for unparsed items
    quantity_max: Optional[float]
    unit: Optional[str]
    raw_texts: list[str] = field(default_factory=list)  # source lines (for unparsed / tooltip)
    parsed: bool = True

    def display_quantity(self) -> str:
        if not self.parsed or self.quantity is None:
            return ""
        text = units.format_quantity(self.quantity)
        if self.quantity_max is not None:
            text += "–" + units.format_quantity(self.quantity_max)
        return text

    def display_unit(self) -> str:
        return units.unit_label(self.unit)


def _normalize_name(name: Optional[str]) -> str:
    """Normalize an ingredient name for merge matching (lowercase, singularize, denoise)."""
    if not name:
        return ""
    text = name.lower().strip()
    # Drop parenthetical notes and common prep words that don't affect identity.
    text = re.sub(r"\(.*?\)", "", text)
    text = re.sub(
        r"\b(fresh|dried|chopped|minced|sliced|diced|ground|grated|large|small|"
        r"medium|ripe|to taste|finely|roughly|plus more|for garnish)\b",
        "",
        text,
    )
    text = re.sub(r"[,.].*$", "", text)  # drop everything after a comma/period
    text = re.sub(r"\s+", " ", text).strip()
    # Naive singularization for matching only.
    if text.endswith("ies") and len(text) > 4:
        text = text[:-3] + "y"
    elif text.endswith("es") and len(text) > 3:
        text = text[:-2]
    elif text.endswith("s") and len(text) > 3:
        text = text[:-1]
    return text


def build_shopping_list(recipes: list[Recipe], system: str) -> list[dict]:
    """Return an ordered list of ``{"aisle": str, "items": [ShoppingItem, ...]}``.

    Only aisles that actually contain items are included.
    """
    # Merge key: (normalized_name, measurement_type). Different measurement types
    # for the same name (e.g. volume vs weight) stay separate.
    merged: dict[tuple[str, str], ShoppingItem] = {}
    unparsed: list[ShoppingItem] = []

    for recipe in recipes:
        for group in recipe.groups:
            for ing in group.ingredients:
                if not ing.parsed or ing.quantity is None or not ing.name:
                    unparsed.append(
                        ShoppingItem(
                            name=(ing.name or ing.raw_text),
                            quantity=None,
                            quantity_max=None,
                            unit=None,
                            raw_texts=[ing.raw_text],
                            parsed=False,
                        )
                    )
                    continue

                norm = _normalize_name(ing.name)
                mtype = units.measurement_type(ing.unit)
                key = (norm, mtype)

                if key not in merged:
                    merged[key] = ShoppingItem(
                        name=ing.name.strip(),
                        quantity=ing.quantity,
                        quantity_max=ing.quantity_max,
                        unit=ing.unit,
                        raw_texts=[ing.raw_text],
                    )
                    continue

                existing = merged[key]
                existing.raw_texts.append(ing.raw_text)
                # Sum by converting the new amount into the existing item's unit.
                add_low = units.convert(ing.quantity, ing.unit, existing.unit)
                if add_low is None:
                    # Shouldn't happen (same mtype), but guard: keep separate.
                    unparsed.append(
                        ShoppingItem(
                            name=ing.name.strip(),
                            quantity=ing.quantity,
                            quantity_max=ing.quantity_max,
                            unit=ing.unit,
                            raw_texts=[ing.raw_text],
                        )
                    )
                    continue
                # Collapse any range into a single summed quantity for shopping.
                existing_val = (existing.quantity or 0)
                if existing.quantity_max is not None:
                    existing_val = existing.quantity_max
                    existing.quantity_max = None
                add_val = add_low
                if ing.quantity_max is not None:
                    add_val = units.convert(ing.quantity_max, ing.unit, existing.unit) or add_low
                existing.quantity = existing_val + add_val

    # Convert merged items into the preferred display system and round.
    items: list[ShoppingItem] = []
    for item in merged.values():
        qty, unit = units.to_system(item.quantity, item.unit, system)
        item.quantity = units.round_cooking(qty, unit)
        item.unit = unit
        items.append(item)

    items.extend(unparsed)

    # Bucket by aisle.
    buckets: dict[str, list[ShoppingItem]] = {a: [] for a in AISLE_ORDER}
    for item in items:
        buckets[categorize(item.name)].append(item)

    result: list[dict] = []
    for aisle in AISLE_ORDER:
        bucket = buckets[aisle]
        if not bucket:
            continue
        bucket.sort(key=lambda it: it.name.lower())
        result.append({"aisle": aisle, "items": bucket})
    return result
