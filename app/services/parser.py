"""Parse a raw ingredient line into structured quantity + unit + name.

Output is a dict with keys: raw_text, quantity, quantity_max, unit, name, parsed.

* ``quantity``      low end of a range, or the single value (float, or None)
* ``quantity_max``  high end when the line was a range like "1-2" (else None)
* ``unit``          canonical unit code (see units.py) or None for count items
* ``name``          the ingredient name (best effort; may equal the whole line)
* ``parsed``        True only when a numeric quantity was extracted

The parser never raises and never blocks saving: if it can't find a quantity it
returns parsed=False with the full line kept as ``name``/``raw_text`` so the UI
can display it verbatim and flag it for manual fixing.
"""
from __future__ import annotations

import re
from typing import Optional

from app.services.units import normalize_unit

# Unicode fractions -> ascii equivalents.
_UNICODE_FRACTIONS = {
    "¼": "1/4", "½": "1/2", "¾": "3/4",
    "⅓": "1/3", "⅔": "2/3",
    "⅕": "1/5", "⅖": "2/5", "⅗": "3/5", "⅘": "4/5",
    "⅙": "1/6", "⅚": "5/6",
    "⅛": "1/8", "⅜": "3/8", "⅝": "5/8", "⅞": "7/8",
}

# Range separators: hyphen variants (which may sit directly between digits, e.g.
# "1-2") and the word "to". The range branch further validates that both sides
# start with a number, so this loose pattern won't misread "all-purpose flour".
_RANGE_RE = re.compile(r"^\s*(.+?)\s*(?:-|–|—|\bto\b)\s*(.+)$")

# A single numeric token: integer, decimal, fraction, or mixed number.
_NUMBER_RE = re.compile(
    r"^\s*(?P<num>\d+\s+\d+/\d+|\d+/\d+|\d*\.\d+|\d+)\s*(?P<rest>.*)$",
    re.DOTALL,
)

# Leading noise sometimes attached before quantities, e.g. "approx. 2 cups".
_LEADING_NOISE_RE = re.compile(
    r"^\s*(about|approx\.?|approximately|around|roughly)\s+", re.IGNORECASE
)


def normalize_unicode_fractions(text: str) -> str:
    """Replace unicode fraction glyphs with ascii, inserting a space if a digit
    immediately precedes them (so "1½" becomes "1 1/2")."""
    out = []
    for i, ch in enumerate(text):
        if ch in _UNICODE_FRACTIONS:
            if out and out[-1].isdigit():
                out.append(" ")
            out.append(_UNICODE_FRACTIONS[ch])
        else:
            out.append(ch)
    return "".join(out)


def _to_float(token: str) -> Optional[float]:
    """Convert an int/decimal/fraction/mixed-number token to a float."""
    token = token.strip()
    if not token:
        return None
    try:
        if " " in token:  # mixed number "1 1/2"
            whole, frac = token.split(None, 1)
            num, denom = frac.split("/")
            return int(whole) + int(num) / int(denom)
        if "/" in token:  # simple fraction
            num, denom = token.split("/")
            return int(num) / int(denom)
        return float(token)
    except (ValueError, ZeroDivisionError):
        return None


def _extract_unit(rest: str) -> tuple[Optional[str], str]:
    """Try to consume a unit from the start of ``rest``.

    Returns (canonical_unit_or_None, remaining_name). Tries a two-word unit
    ("fluid ounce", "fl oz") before a one-word unit so multi-word units win.
    """
    rest = rest.strip()
    if not rest:
        return None, ""

    tokens = rest.split()

    # Two-word unit (e.g. "fluid ounces", "fl oz").
    if len(tokens) >= 2:
        two = f"{tokens[0]} {tokens[1]}".lower().strip(".")
        unit = normalize_unit(two)
        if unit:
            return unit, " ".join(tokens[2:]).strip()

    one = tokens[0].lower().strip(".")
    unit = normalize_unit(one)
    if unit:
        return unit, " ".join(tokens[1:]).strip()

    return None, rest


def _clean_name(name: str) -> str:
    """Tidy an extracted ingredient name."""
    name = name.strip()
    # Drop a single leading "of " ("2 cups of flour" -> "flour").
    name = re.sub(r"^of\s+", "", name, flags=re.IGNORECASE)
    # Collapse whitespace.
    name = re.sub(r"\s+", " ", name)
    return name.strip(" ,")


def parse_ingredient(raw: str) -> dict:
    """Parse one ingredient line into structured fields (see module docstring)."""
    raw_text = (raw or "").strip()
    result = {
        "raw_text": raw_text,
        "quantity": None,
        "quantity_max": None,
        "unit": None,
        "name": raw_text or None,
        "parsed": False,
    }
    if not raw_text:
        return result

    work = normalize_unicode_fractions(raw_text)
    work = _LEADING_NOISE_RE.sub("", work)

    # Detect a leading range like "1-2 cups" / "1 to 2 cups".
    quantity: Optional[float] = None
    quantity_max: Optional[float] = None
    rest = work

    range_match = _RANGE_RE.match(work)
    if range_match:
        low_raw, high_rest = range_match.group(1), range_match.group(2)
        low_match = _NUMBER_RE.match(low_raw)
        high_match = _NUMBER_RE.match(high_rest)
        # Only treat as a range if BOTH sides start with a number and the low
        # side is purely a number (otherwise "salt - to taste" isn't a range).
        if low_match and high_match and not low_match.group("rest").strip():
            quantity = _to_float(low_match.group("num"))
            quantity_max = _to_float(high_match.group("num"))
            rest = high_match.group("rest")

    if quantity is None:
        num_match = _NUMBER_RE.match(work)
        if num_match:
            quantity = _to_float(num_match.group("num"))
            rest = num_match.group("rest")

    if quantity is None:
        # No numeric quantity -> unparsed (still fine to save/display).
        result["name"] = _clean_name(work) or raw_text
        return result

    unit, name = _extract_unit(rest)
    result["quantity"] = quantity
    result["quantity_max"] = quantity_max
    result["unit"] = unit
    result["name"] = _clean_name(name) or None
    result["parsed"] = True
    return result
