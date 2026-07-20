"""Build an aisle-grouped view of the persistent shopping list for display.

The list itself is stored as discrete ``ShoppingListItem`` rows (see
``app.models``). New lines are folded into a matching existing row when
possible (see ``crud.add_shopping_item``, which uses ``normalize_name`` below
to decide what "matching" means) -- rendering here just converts each row's
quantity into the requested unit system and buckets rows by grocery aisle.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from app.models import ShoppingListItem
from app.services import units
from app.services.aisles import AISLE_ORDER, categorize

# Words that don't affect an ingredient's identity for merge-matching purposes
# (e.g. "chopped onion" and "onion" should combine into one line).
_NOISE_WORDS_RE = re.compile(
    r"\b(fresh|dried|chopped|minced|sliced|diced|ground|grated|large|small|"
    r"medium|ripe|finely|roughly|for garnish)\b"
)


def normalize_name(name: Optional[str]) -> str:
    """Normalize an ingredient name for merge matching.

    Lowercases, drops parentheticals and common prep/size adjectives, strips
    anything after a comma/period, and naively singularizes -- so "2 Large
    Onions, diced" and "onion" both normalize to "onion" and can be combined.
    """
    if not name:
        return ""
    text = name.lower().strip()
    text = re.sub(r"\(.*?\)", "", text)
    text = _NOISE_WORDS_RE.sub("", text)
    text = re.sub(r"[,.].*$", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    if text.endswith("ies") and len(text) > 4:
        text = text[:-3] + "y"
    elif text.endswith("es") and len(text) > 3:
        text = text[:-2]
    elif text.endswith("s") and len(text) > 3:
        text = text[:-1]
    return text


@dataclass
class DisplayItem:
    """A shopping-list row with its quantity converted for display."""

    id: int
    name: str
    note: Optional[str]
    source: Optional[str]
    checked: bool
    quantity: Optional[float]
    quantity_max: Optional[float]
    unit: Optional[str]

    def display_quantity(self) -> str:
        if self.quantity is None:
            return ""
        text = units.format_quantity(self.quantity)
        if self.quantity_max is not None:
            text += "–" + units.format_quantity(self.quantity_max)
        return text

    def display_unit(self) -> str:
        return units.unit_label(self.unit)


def _to_display(item: ShoppingListItem, system: str) -> DisplayItem:
    qty, qty_max, unit = item.quantity, item.quantity_max, item.unit
    if qty is not None:
        qty, unit = units.to_system(qty, unit, system)
        qty = units.round_cooking(qty, unit)
        if qty_max is not None:
            qty_max, _ = units.to_system(item.quantity_max, item.unit, system)
            qty_max = units.round_cooking(qty_max, unit)
    return DisplayItem(
        id=item.id,
        name=item.name,
        note=item.note,
        source=item.source,
        checked=item.checked,
        quantity=qty,
        quantity_max=qty_max,
        unit=unit,
    )


def build_shopping_view(items: list[ShoppingListItem], system: str) -> list[dict]:
    """Return an ordered list of ``{"aisle": str, "items": [DisplayItem, ...]}``.

    Only aisles that actually contain items are included. Within an aisle,
    unchecked items sort first, then alphabetically by name.
    """
    buckets: dict[str, list[DisplayItem]] = {a: [] for a in AISLE_ORDER}
    for item in items:
        buckets[categorize(item.name)].append(_to_display(item, system))

    result: list[dict] = []
    for aisle in AISLE_ORDER:
        bucket = buckets[aisle]
        if not bucket:
            continue
        bucket.sort(key=lambda it: (it.checked, it.name.lower()))
        result.append({"aisle": aisle, "items": bucket})
    return result
