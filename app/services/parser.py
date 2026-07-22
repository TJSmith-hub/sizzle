"""Parse a raw ingredient line into structured quantity + unit + name.

Output is a dict with keys: raw_text, quantity, quantity_max, unit, name, note, parsed.

* ``quantity``      low end of a range, or the single value (float, or None)
* ``quantity_max``  high end when the line was a range like "1-2" (else None)
* ``unit``          canonical unit code (see units.py) or None for count items
* ``name``          the ingredient itself (best effort; may equal the whole line)
* ``note``          a trailing preparation note ("finely chopped"), or None
* ``parsed``        True only when a numeric quantity was extracted

The parser never raises and never blocks saving: if it can't find a quantity it
returns parsed=False with the full line kept as ``name``/``raw_text`` so the UI
can display it verbatim and flag it for manual fixing.
"""
from __future__ import annotations

import re

from app.services.units import UNIT_WORDS, normalize_unit

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

# Single-token unit words (longest first), used to spot a unit right after a
# number, e.g. the "g"/"oz" in a "100g/3.5oz" dual measurement.
_UNIT_ALT = "|".join(
    sorted(
        (re.escape(u) for u in UNIT_WORDS if " " not in u and u != "#"),
        key=len,
        reverse=True,
    )
)

# A quantity written twice in different units, joined by "/" (e.g. "100g/3.5oz"
# or "1 lb / 450 g"). Recipes often list both metric and imperial; we keep the
# first value and drop the redundant alternate, since the app converts units for
# display itself. The leading number must be immediately followed by a unit, so
# a bare fraction ("1/2 cup") or mixed number ("1 1/2 tbsp") never matches.
_DUAL_MEASURE_RE = re.compile(
    rf"^(?P<keep>\s*\d*\.?\d+\s*(?:{_UNIT_ALT})\b)\s*/\s*\d*\.?\d+\s*(?:{_UNIT_ALT})\b",
    re.IGNORECASE,
)


def _strip_dual_measure(text: str) -> str:
    """Reduce a "100g/3.5oz" style dual measurement to just its first value."""
    return _DUAL_MEASURE_RE.sub(lambda m: m.group("keep") + " ", text, count=1)


def normalize_unicode_fractions(text: str) -> str:
    """Replace unicode fraction glyphs with ascii equivalents.

    Inserts a space if a digit immediately precedes the glyph (so "1½" becomes
    "1 1/2").
    """
    out = []
    for ch in text:
        if ch in _UNICODE_FRACTIONS:
            if out and out[-1].isdigit():
                out.append(" ")
            out.append(_UNICODE_FRACTIONS[ch])
        else:
            out.append(ch)
    return "".join(out)


def _to_float(token: str) -> float | None:
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


def _extract_unit(rest: str) -> tuple[str | None, str]:
    """Try to consume a unit from the start of ``rest``.

    Returns (canonical_unit_or_None, remaining_name). Tries a two-word unit
    ("fluid ounce", "fl oz") before a one-word unit so multi-word units win.
    """
    rest = rest.strip()
    if not rest:
        return None, ""

    tokens = rest.split()

    # Two-word unit (e.g. "fluid ounces", "fl oz", "fl. oz."). Strip periods off
    # each token before rejoining, so an interior period ("fl. oz.") doesn't
    # defeat the lookup the way strip(".") on the joined string would.
    if len(tokens) >= 2:
        two = f"{tokens[0].strip('.')} {tokens[1].strip('.')}".lower()
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


# Words that, appearing at the END of an ingredient name, mark a preparation
# note ("finely chopped", "peeled and diced") rather than the ingredient itself.
_PREP_WORDS = {
    "chopped", "minced", "sliced", "diced", "grated", "shredded", "crushed",
    "crumbled", "melted", "softened", "beaten", "whisked", "peeled", "seeded",
    "deseeded", "cored", "trimmed", "halved", "quartered", "cubed", "julienned",
    "mashed", "drained", "rinsed", "cooked", "toasted", "roasted", "cooled",
    "warmed", "chilled", "thawed", "sifted", "packed", "divided", "separated",
    "torn", "snipped", "zested", "juiced", "pitted", "stemmed", "hulled",
    "blanched", "steamed", "boiled", "dissolved", "scored", "deveined",
    "shelled", "pounded", "flattened", "brushed", "squeezed", "deboned",
    "boned", "skinned", "patted", "washed", "picked", "cleaned",
}

# Adverbs/connectors that can sit inside a trailing prep phrase, but only count
# as note material when a real prep word is also present in that trailing run
# (so "very ripe banana" is left alone, but "finely chopped" is peeled off).
_PREP_MODIFIERS = {
    "finely", "roughly", "coarsely", "thinly", "thickly", "freshly", "lightly",
    "well", "very", "and", "or", "then", "plus", "slightly", "evenly",
    "preferably", "ideally", "about",
}


def _is_alternative(text: str) -> bool:
    """Return True if a trailing fragment is an ingredient alternative.

    An alternative ("or spinach") rather than a preparation instruction stays
    part of the name, so "(or spinach)" behaves the same as an inline
    "tamari or soy sauce".
    """
    t = text.strip().lower()
    return t == "or" or t.startswith("or ")


def _split_trailing_paren(name: str) -> tuple[str, str | None]:
    """Peel a balanced parenthetical off the END of a name into a note.

    "garlic clove (finely minced)" -> ("garlic clove", "finely minced"). A paren
    that isn't at the end (e.g. "1 can (400g) tomatoes") is left untouched, and a
    parenthetical alternative ("pak choi (or spinach)") stays in the name.
    """
    name = name.strip()
    if not name.endswith(")"):
        return name, None
    depth = 0
    for idx in range(len(name) - 1, -1, -1):
        ch = name[idx]
        if ch == ")":
            depth += 1
        elif ch == "(":
            depth -= 1
            if depth == 0:
                inside = name[idx + 1 : -1].strip(" ,;")
                head = name[:idx].strip(" ,")
                if head and inside and not _is_alternative(inside):
                    return head, inside
                return name, None
    return name, None  # unbalanced parens -> leave as-is


def _split_comma_or_prep(name: str) -> tuple[str, str | None]:
    """Separate a name from a trailing prep note via a comma, else prep words."""
    name = name.strip()
    if not name:
        return name, None

    # Strong signal: a comma separates the ingredient from its preparation.
    if "," in name:
        head, _, tail = name.partition(",")
        head = head.strip(" ,")
        tail = tail.strip(" ,")
        # "onion, or shallot" is an alternative ingredient -> keep the whole name.
        if head and not _is_alternative(tail):
            return head, (tail or None)

    # Otherwise peel a trailing run of prep words (must include a real prep word).
    tokens = name.split()
    i = len(tokens)
    saw_prep = False
    while i > 0:
        word = tokens[i - 1].lower().strip(".,;:()")
        if word in _PREP_WORDS:
            saw_prep = True
            i -= 1
        elif word in _PREP_MODIFIERS and saw_prep:
            i -= 1
        else:
            break
    if saw_prep and 0 < i < len(tokens):
        head = " ".join(tokens[:i]).strip(" ,")
        tail = " ".join(tokens[i:]).strip(" ,")
        if head and not _is_alternative(tail):
            return head, (tail or None)
    return name, None


def _lowercase(name: str | None) -> str | None:
    """Lowercase an ingredient name so imported lines read consistently."""
    if not name:
        return name
    return name.lower()


def _split_name_note(name: str) -> tuple[str, str | None]:
    """Separate an ingredient name from a trailing preparation note.

    Handles three common shapes, in order: a trailing parenthetical
    ("garlic clove (finely minced)"), a comma ("garlic clove, finely chopped"),
    and a trailing run of prep words ("garlic clove finely chopped"). The name is
    never reduced to empty -- if the whole thing reads like prep, it stays as the
    name for the user to fix on the review screen.
    """
    head, paren_note = _split_trailing_paren(name)
    name, note = _split_comma_or_prep(head)
    notes = [n.strip(" ,;") for n in (note, paren_note) if n and n.strip(" ,;")]
    return name, ("; ".join(notes) if notes else None)


def parse_ingredient(raw: str) -> dict:
    """Parse one ingredient line into structured fields (see module docstring)."""
    raw_text = (raw or "").strip()
    result = {
        "raw_text": raw_text,
        "quantity": None,
        "quantity_max": None,
        "unit": None,
        "name": raw_text or None,
        "note": None,
        "parsed": False,
    }
    if not raw_text:
        return result

    work = normalize_unicode_fractions(raw_text)
    work = _LEADING_NOISE_RE.sub("", work)
    work = _strip_dual_measure(work)

    # Detect a leading range like "1-2 cups" / "1 to 2 cups".
    quantity: float | None = None
    quantity_max: float | None = None
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
        name, note = _split_name_note(_clean_name(work))
        result["name"] = _lowercase(name or raw_text)
        result["note"] = note
        return result

    unit, name = _extract_unit(rest)
    name, note = _split_name_note(_clean_name(name))
    result["quantity"] = quantity
    result["quantity_max"] = quantity_max
    result["unit"] = unit
    result["name"] = _lowercase(name) or None
    result["note"] = note
    result["parsed"] = True
    return result
