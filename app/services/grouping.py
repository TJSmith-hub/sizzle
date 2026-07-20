"""Split a flat list of ingredient strings into named groups.

Scraped ingredient lists are flat, but many recipes are sectioned ("For the
dough", "For the filling"). Those headers usually appear *in the list itself* as
entries with no quantity (e.g. "For the sauce:"). This module detects those
headers heuristically and splits the list accordingly.

--------------------------------------------------------------------------
TUNING
--------------------------------------------------------------------------
Adjust the constants below to change how aggressively headers are detected.
The heuristic is intentionally CONSERVATIVE by default: it is better to miss a
header (the user adds a group on the review screen) than to wrongly split a real
ingredient like "salt" into its own section.

* HEADER_MAX_LEN            - max characters for the "short line" rules.
* HEADER_PREFIXES           - lowercase prefixes that mark a header.
* ENABLE_SHORT_PHRASE_RULE  - if True, also treat a short, unit-free, digit-free
                              line as a header. OFF by default because it
                              false-positives on single-word ingredients.
--------------------------------------------------------------------------
"""
from __future__ import annotations

import re
from typing import Optional

from app.services.units import UNIT_WORDS

HEADER_MAX_LEN = 40

HEADER_PREFIXES = (
    "for the ",
    "for ",
    "to serve",
    "to garnish",
    "to finish",
    "to decorate",
    "optional",
    "topping",
    "toppings",
    "garnish",
)

ENABLE_SHORT_PHRASE_RULE = False

_DIGIT_RE = re.compile(r"\d")
_WORD_RE = re.compile(r"[a-zA-Z]+")


def _contains_unit_word(line: str) -> bool:
    words = {w.lower() for w in _WORD_RE.findall(line)}
    return bool(words & UNIT_WORDS)


def is_header(line: str) -> bool:
    """Return True if a line looks like a section header rather than an ingredient."""
    text = line.strip()
    if not text:
        return False

    lower = text.lower()

    # Rule 1: ends with a colon -> almost always a header ("For the sauce:").
    if text.endswith(":"):
        return True

    # Rule 2: matches a known header prefix ("for the ...", "to serve", etc.).
    if any(lower.startswith(p) for p in HEADER_PREFIXES):
        return True

    # Headers never contain digits (quantities). Anything numeric is an ingredient.
    if _DIGIT_RE.search(text):
        return False

    # Rule 3: ALL CAPS heading (and reasonably short), e.g. "DOUGH".
    letters = _WORD_RE.findall(text)
    if letters and text.upper() == text and len(text) <= HEADER_MAX_LEN:
        return True

    # Rule 4 (opt-in): short line, no unit words -> treat as a header. This is
    # disabled by default because it misclassifies bare ingredients ("salt").
    if ENABLE_SHORT_PHRASE_RULE:
        if len(text) <= HEADER_MAX_LEN and not _contains_unit_word(text):
            return True

    return False


def _clean_title(header_line: str) -> str:
    """Turn a header line into a group title (strip trailing colon/whitespace)."""
    return header_line.strip().rstrip(":").strip()


def group_ingredients(lines: list[str]) -> list[dict]:
    """Split raw ingredient lines into ordered groups.

    Returns a list of ``{"title": Optional[str], "ingredients": list[str]}``.
    Lines appearing before the first detected header go into a leading group with
    ``title=None`` (the default/ungrouped section). That group is only included if
    it actually contains ingredients.
    """
    groups: list[dict] = []
    current: dict = {"title": None, "ingredients": []}

    for raw in lines:
        line = (raw or "").strip()
        if not line:
            continue
        if is_header(line):
            # Close the current group if it has content, then start a new one.
            if current["ingredients"] or current["title"] is not None:
                groups.append(current)
            current = {"title": _clean_title(line), "ingredients": []}
        else:
            current["ingredients"].append(line)

    if current["ingredients"] or current["title"] is not None:
        groups.append(current)

    # Drop a leading untitled group that ended up empty (e.g. list started with a header).
    groups = [g for g in groups if g["ingredients"] or g["title"]]

    # If nothing was detected at all, return a single default group.
    if not groups:
        return [{"title": None, "ingredients": []}]

    return groups
