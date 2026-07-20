"""Fetch a recipe URL and normalize it using the recipe-scrapers library.

recipe-scrapers supports hundreds of named sites and, via ``wild_mode=True``,
falls back to generic schema.org / JSON-LD ``Recipe`` parsing for the rest.

We fetch the HTML ourselves with a browser-like User-Agent (many sites 403 the
default client UA) and then hand the HTML to ``scrape_html`` so scraping never
depends on the library's own networking.
"""
from __future__ import annotations

import re

import httpx
from recipe_scrapers import scrape_html

from app.config import FETCH_TIMEOUT, FETCH_USER_AGENT
from app.services.grouping import group_ingredients
from app.services.parser import parse_ingredient


class ScrapeError(Exception):
    """Raised when a URL cannot be fetched or no usable recipe data is found."""


def _fetch_html(url: str) -> str:
    headers = {
        "User-Agent": FETCH_USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-GB,en;q=0.9",
    }
    try:
        with httpx.Client(
            headers=headers, timeout=FETCH_TIMEOUT, follow_redirects=True
        ) as client:
            resp = client.get(url)
            resp.raise_for_status()
            return resp.text
    except httpx.HTTPStatusError as exc:
        raise ScrapeError(
            f"The page returned HTTP {exc.response.status_code}. "
            "The site may be blocking automated access."
        ) from exc
    except httpx.HTTPError as exc:
        raise ScrapeError(f"Could not fetch the page: {exc}") from exc


def _safe(fn, default=None):
    """Call a scraper method, swallowing the exceptions it raises for missing fields."""
    try:
        value = fn()
    except Exception:  # noqa: BLE001 - scraper plugins raise assorted errors for missing fields
        return default
    return value if value is not None else default


_SERVINGS_RE = re.compile(r"\d+")


def _parse_servings(yields: str | None) -> int | None:
    """Extract an integer serving count from a yields string like '4 servings'."""
    if not yields:
        return None
    if isinstance(yields, int):
        return yields
    m = _SERVINGS_RE.search(str(yields))
    return int(m.group()) if m else None


def _positive_int(value) -> int | None:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return None
    return n if n > 0 else None


def _norm(text: str) -> str:
    """Normalize a line for comparison (collapse whitespace, lowercase)."""
    return re.sub(r"\s+", " ", text or "").strip().lower()


def _has_sections(groups: list | None) -> bool:
    """Return True if at least one group carries a real section title."""
    return bool(groups) and any(g["title"] for g in groups)


def _native_groups(scraper) -> list | None:
    """Use recipe-scrapers' own ``ingredient_groups()`` when the site supports it.

    Returns a list of ``{"title": str|None, "lines": [str, ...]}`` or None when
    the method is unavailable or raises (some site plugins error on pages whose
    markup no longer matches their hardcoded selectors).
    """
    try:
        groups = scraper.ingredient_groups()
    except Exception:  # noqa: BLE001 - plugins raise assorted errors
        return None
    out = []
    for g in groups or []:
        lines = [str(x) for x in getattr(g, "ingredients", []) if str(x).strip()]
        if not lines:
            continue
        purpose = getattr(g, "purpose", None)
        out.append({"title": (purpose or None), "lines": lines})
    return out or None


def _soup_groups(scraper, flat: list[str]) -> list | None:
    """Reconstruct sections from the page HTML via each list's sibling heading.

    Matches ingredient lists to their nearest sibling heading. Works even when
    the library's per-site grouping fails: we locate the
    ``<ul>``/``<ol>`` lists whose items match the flat ingredient list, then take
    each list's preceding-sibling heading (scoped to the same container, so we
    never grab an unrelated page heading like "Nutrition"). Falls back to None if
    it can't account for most of the ingredients.
    """
    soup = getattr(scraper, "soup", None)
    if soup is None or not flat:
        return None

    flat_set = {_norm(x) for x in flat}
    out = []
    for lst in soup.find_all(["ul", "ol"]):
        items = lst.find_all("li", recursive=False) or lst.find_all("li")
        texts = [li.get_text(" ", strip=True) for li in items]
        matched = [t for t in texts if _norm(t) in flat_set]
        # Skip lists that aren't (mostly) ingredients — e.g. nav or nutrition.
        if not matched or len(matched) < max(1, len(texts) // 2):
            continue
        heading = lst.find_previous_sibling(["h2", "h3", "h4", "h5", "h6"])
        title = heading.get_text(" ", strip=True) if heading else None
        # A heading that is itself an ingredient, or absurdly long, isn't a section.
        if title and (len(title) > 60 or _norm(title) in flat_set):
            title = None
        out.append({"title": title, "lines": matched})

    covered = sum(len(g["lines"]) for g in out)
    if covered < len(flat) * 0.6:  # didn't reliably map the list — bail out
        return None
    return out or None


def _build_groups(scraper, flat: list[str]) -> list[dict]:
    """Return grouped, parsed ingredients, preferring real site sections.

    Strategy (most reliable first): the library's native ``ingredient_groups()``,
    then an HTML/soup reconstruction, then our text-only heuristic on the flat
    list. The first strategy that actually finds titled sections wins.
    """
    raw = _native_groups(scraper)
    if not _has_sections(raw):
        soup_based = _soup_groups(scraper, flat)
        if _has_sections(soup_based):
            raw = soup_based
    if not _has_sections(raw):
        raw = [
            {"title": g["title"], "lines": g["ingredients"]}
            for g in group_ingredients(flat)
        ]

    return [
        {
            "title": g["title"],
            "ingredients": [parse_ingredient(line) for line in g["lines"]],
        }
        for g in raw
    ]


def scrape_recipe(url: str) -> dict:
    """Scrape ``url`` and return a normalized, structured recipe dict.

    Shape::

        {
          "title", "source_url", "image_url", "servings",
          "prep_time", "cook_time", "total_time",
          "instructions": [str, ...],
          "groups": [ {"title": str|None, "ingredients": [parsed_dict, ...]} ],
        }

    Raises ScrapeError if the page can't be fetched or has no title/ingredients.
    """
    url = url.strip()
    if not url:
        raise ScrapeError("Please enter a URL.")
    if not url.lower().startswith(("http://", "https://")):
        url = "https://" + url

    html = _fetch_html(url)

    try:
        scraper = scrape_html(html, org_url=url, wild_mode=True)
    except Exception as exc:
        raise ScrapeError(
            "Couldn't find recipe data on that page. It may not be a recipe "
            "page, or the site's format isn't supported."
        ) from exc

    title = _safe(scraper.title)
    ingredients = _safe(scraper.ingredients, default=[]) or []

    if not title and not ingredients:
        raise ScrapeError(
            "Couldn't find a recipe on that page (no title or ingredients). "
            "You can still add it manually."
        )

    instructions = _safe(scraper.instructions_list, default=None)
    if not instructions:
        text = _safe(scraper.instructions, default="") or ""
        instructions = [s.strip() for s in text.split("\n") if s.strip()]

    # Reconstruct ingredient sections (preferring the site's own grouping), then
    # parse each line into structured fields.
    groups = _build_groups(scraper, [str(i) for i in ingredients])

    return {
        "title": title or "Untitled recipe",
        "source_url": url,
        "image_url": _safe(scraper.image),
        "servings": _parse_servings(_safe(scraper.yields)),
        "prep_time": _positive_int(_safe(scraper.prep_time)),
        "cook_time": _positive_int(_safe(scraper.cook_time)),
        "total_time": _positive_int(_safe(scraper.total_time)),
        "instructions": instructions,
        "groups": groups,
    }
