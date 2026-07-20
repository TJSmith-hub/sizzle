"""Units: normalization, conversion, system selection, temperature, and rounding.

Design
------
* Units are normalized to a small fixed set of canonical codes (see ``UNITS``).
* Each unit belongs to a *measurement type*: "volume", "weight", or "count".
* Conversion is only ever performed **within the same measurement type**
  (volume <-> volume, weight <-> weight). Volume <-> weight is density dependent
  and deliberately NOT attempted anywhere in this codebase.
* Volume converts through a base of millilitres; weight through a base of grams.

The Python rounding/formatting helpers here are mirrored by ``static/js/scale.js``
so that server-side (shopping list) and client-side (live scaling) output agree.
"""
from __future__ import annotations

import re
from fractions import Fraction
from typing import Optional

# --- Canonical units -------------------------------------------------------

VOLUME = "volume"
WEIGHT = "weight"
COUNT = "count"

# Canonical unit -> measurement type.
UNIT_TYPE: dict[str, str] = {
    "tsp": VOLUME,
    "tbsp": VOLUME,
    "cup": VOLUME,
    "fl_oz": VOLUME,
    "ml": VOLUME,
    "l": VOLUME,
    "g": WEIGHT,
    "kg": WEIGHT,
    "oz": WEIGHT,
    "lb": WEIGHT,
}

# Factor to convert 1 <unit> into the base unit of its type (ml for volume, g for weight).
TO_BASE: dict[str, float] = {
    # volume -> ml
    "tsp": 4.92892,
    "tbsp": 14.7868,
    "fl_oz": 29.5735,
    "cup": 236.588,
    "ml": 1.0,
    "l": 1000.0,
    # weight -> g
    "g": 1.0,
    "kg": 1000.0,
    "oz": 28.3495,
    "lb": 453.592,
}

# Which system each unit belongs to (used when picking a display unit).
METRIC_UNITS = {"ml", "l", "g", "kg"}
IMPERIAL_UNITS = {"tsp", "tbsp", "cup", "fl_oz", "oz", "lb"}

# Map many written forms -> canonical unit. Longer / more specific keys are
# matched first (see ``normalize_unit``). Keep additions lowercase.
UNIT_SYNONYMS: dict[str, str] = {
    "teaspoons": "tsp", "teaspoon": "tsp", "tsps": "tsp", "tsp": "tsp", "tsp.": "tsp",
    "tablespoons": "tbsp", "tablespoon": "tbsp", "tbsps": "tbsp", "tbsp": "tbsp",
    "tbsp.": "tbsp", "tbs": "tbsp", "tbl": "tbsp",
    "cups": "cup", "cup": "cup", "c": "cup",
    "fluid ounces": "fl_oz", "fluid ounce": "fl_oz", "fl oz": "fl_oz",
    "fl. oz.": "fl_oz", "fl oz.": "fl_oz", "floz": "fl_oz", "fl_oz": "fl_oz",
    "millilitres": "ml", "milliliters": "ml", "millilitre": "ml", "milliliter": "ml",
    "ml": "ml", "mls": "ml", "cc": "ml",
    "litres": "l", "liters": "l", "litre": "l", "liter": "l", "l": "l",
    "grams": "g", "gram": "g", "gr": "g", "g": "g", "gm": "g", "gms": "g",
    "kilograms": "kg", "kilogram": "kg", "kilo": "kg", "kilos": "kg",
    "kgs": "kg", "kg": "kg",
    # "ounce"/"oz" default to WEIGHT; fluid ounces are handled by the fl_oz keys above.
    "ounces": "oz", "ounce": "oz", "ozs": "oz", "oz": "oz", "oz.": "oz",
    "pounds": "lb", "pound": "lb", "lbs": "lb", "lb": "lb", "lb.": "lb", "#": "lb",
}

# Set of unit *words* (any synonym), used by the grouping heuristic to decide
# whether a line "contains a unit" (and is therefore probably an ingredient).
UNIT_WORDS: set[str] = set(UNIT_SYNONYMS.keys())


def normalize_unit(token: str) -> Optional[str]:
    """Return the canonical unit for a written token, or None if unrecognized."""
    if not token:
        return None
    key = token.strip().lower()
    return UNIT_SYNONYMS.get(key)


def measurement_type(unit: Optional[str]) -> str:
    """Return the measurement type for a canonical unit ('count' when unit is None)."""
    if unit is None:
        return COUNT
    return UNIT_TYPE.get(unit, COUNT)


def compatible(unit_a: Optional[str], unit_b: Optional[str]) -> bool:
    """True when two units can be summed/converted (same measurement type)."""
    return measurement_type(unit_a) == measurement_type(unit_b)


def convert(quantity: float, from_unit: Optional[str], to_unit: Optional[str]) -> Optional[float]:
    """Convert a quantity between two units of the SAME measurement type.

    Returns None if the units are of different types (e.g. volume vs weight) or
    unknown. Count<->count (both None) returns the quantity unchanged.
    """
    if from_unit == to_unit:
        return quantity
    if not compatible(from_unit, to_unit):
        return None
    if from_unit is None or to_unit is None:
        # One is count and the other isn't -> incompatible (already covered above,
        # but guards against count<->count reaching TO_BASE lookups).
        return quantity if from_unit == to_unit else None
    base = quantity * TO_BASE[from_unit]
    return base / TO_BASE[to_unit]


# --- Choosing a display unit for a target system ---------------------------

def to_system(quantity: float, unit: Optional[str], system: str) -> tuple[float, Optional[str]]:
    """Convert a (quantity, unit) into the most sensible unit for ``system``.

    Rules:
    * Count items (unit is None) are returned unchanged.
    * If the unit already belongs to the requested system, it is kept as-is
      (we only rescale between e.g. g<->kg to keep numbers readable).
    * Otherwise convert within the same measurement type and pick a readable unit.
    Volume is never converted to weight or vice versa.
    """
    system = system.lower()
    mtype = measurement_type(unit)
    if mtype == COUNT or unit is None:
        return quantity, unit

    want_metric = system == "metric"

    if mtype == VOLUME:
        base_ml = quantity * TO_BASE[unit]
        if want_metric:
            # ml, promote to litres at >= 1000 ml.
            if base_ml >= 1000:
                return base_ml / 1000.0, "l"
            return base_ml, "ml"
        # Imperial volume: choose the largest unit that yields a quantity >= 1,
        # falling back to tsp for very small amounts.
        for u in ("cup", "fl_oz", "tbsp", "tsp"):
            val = base_ml / TO_BASE[u]
            if val >= 1:
                return val, u
        return base_ml / TO_BASE["tsp"], "tsp"

    # WEIGHT
    base_g = quantity * TO_BASE[unit]
    if want_metric:
        if base_g >= 1000:
            return base_g / 1000.0, "kg"
        return base_g, "g"
    # Imperial weight: use lb at >= 16 oz, else oz.
    oz = base_g / TO_BASE["oz"]
    if oz >= 16:
        return oz / 16.0, "lb"
    return oz, "oz"


# --- Human-friendly display labels -----------------------------------------

UNIT_LABELS: dict[str, str] = {
    "tsp": "tsp",
    "tbsp": "tbsp",
    "cup": "cup",
    "fl_oz": "fl oz",
    "ml": "ml",
    "l": "l",
    "g": "g",
    "kg": "kg",
    "oz": "oz",
    "lb": "lb",
}


def unit_label(unit: Optional[str]) -> str:
    """Human-readable label for a canonical unit ('' for count/None)."""
    if unit is None:
        return ""
    return UNIT_LABELS.get(unit, unit)


# --- Rounding & formatting (mirrored in scale.js) --------------------------

# Units for which we round to nice cooking fractions (nearest 1/4).
FRACTION_UNITS = {"tsp", "tbsp", "cup"}


def round_cooking(quantity: float, unit: Optional[str]) -> float:
    """Round a quantity to a sensible cooking precision for its unit.

    * tsp/tbsp/cup and unitless counts -> nearest 1/4.
    * ml/g -> nearest whole (nearest 5 at >= 100 to avoid false precision).
    * l/kg/oz/lb/fl_oz -> nearest 0.1.
    """
    if quantity is None:
        return quantity
    mtype = measurement_type(unit)
    if unit in FRACTION_UNITS or mtype == COUNT:
        return round(quantity * 4) / 4
    if unit in ("ml", "g"):
        if quantity >= 100:
            return float(round(quantity / 5) * 5)
        return float(round(quantity))
    return round(quantity, 1)


# Denominators allowed when rendering a decimal as a cooking fraction.
_FRACTION_DENOMS = (2, 3, 4, 8)


def format_quantity(quantity: Optional[float]) -> str:
    """Render a numeric quantity as a friendly string (e.g. 1.5 -> '1 1/2')."""
    if quantity is None:
        return ""
    if quantity < 0:
        return f"-{format_quantity(-quantity)}"

    whole = int(quantity)
    frac = quantity - whole

    if frac < 1e-6:
        return str(whole)

    # Try to snap the fractional part to a small cooking fraction.
    best: Optional[Fraction] = None
    best_err = 1e9
    for denom in _FRACTION_DENOMS:
        num = round(frac * denom)
        if num == 0:
            continue
        cand = Fraction(num, denom)
        err = abs(float(cand) - frac)
        if err < best_err - 1e-9:
            best_err = err
            best = cand

    # If no clean fraction is close enough, fall back to a trimmed decimal.
    if best is None or best_err > 0.06:
        text = f"{quantity:.2f}".rstrip("0").rstrip(".")
        return text

    if best.numerator >= best.denominator:  # rounded up to a whole
        whole += best.numerator // best.denominator
        remainder = best.numerator % best.denominator
        if remainder == 0:
            return str(whole)
        best = Fraction(remainder, best.denominator)

    frac_str = f"{best.numerator}/{best.denominator}"
    return f"{whole} {frac_str}" if whole else frac_str


# --- Temperature conversion (for oven temps in instructions) ----------------

# Matches "180C", "180 °C", "350 F", "350 degrees F", "gas mark" left untouched.
_TEMP_RE = re.compile(
    r"(?P<value>-?\d{2,3})\s*(?:°|degrees?\s*)?\s*(?P<unit>[CF])\b",
    re.IGNORECASE,
)


def convert_temperatures(text: str, system: str) -> str:
    """Rewrite oven temperatures in a block of instruction text to ``system``.

    metric -> Celsius, imperial -> Fahrenheit. Values already in the target
    scale are left unchanged. Rounds C to nearest 5, F to nearest 5.
    """
    system = system.lower()
    target = "C" if system == "metric" else "F"

    def _sub(m: re.Match) -> str:
        value = float(m.group("value"))
        src = m.group("unit").upper()
        if src == target:
            return m.group(0)
        if src == "F":  # -> C
            c = (value - 32) * 5.0 / 9.0
            return f"{int(round(c / 5.0) * 5)}°C"
        # C -> F
        f = value * 9.0 / 5.0 + 32
        return f"{int(round(f / 5.0) * 5)}°F"

    return _TEMP_RE.sub(_sub, text)
