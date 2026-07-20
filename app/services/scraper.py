"""Fetch a recipe URL and normalize it using the recipe-scrapers library.

recipe-scrapers supports hundreds of named sites and, via ``wild_mode=True``,
falls back to generic schema.org / JSON-LD ``Recipe`` parsing for the rest.

We fetch the HTML ourselves with a browser-like User-Agent (many sites 403 the
default client UA) and then hand the HTML to ``scrape_html`` so scraping never
depends on the library's own networking.
"""
from __future__ import annotations

import re
from typing import Optional

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
    except Exception:
        return default
    return value if value is not None else default


_SERVINGS_RE = re.compile(r"\d+")


def _parse_servings(yields: Optional[str]) -> Optional[int]:
    """Extract an integer serving count from a yields string like '4 servings'."""
    if not yields:
        return None
    if isinstance(yields, int):
        return yields
    m = _SERVINGS_RE.search(str(yields))
    return int(m.group()) if m else None


def _positive_int(value) -> Optional[int]:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return None
    return n if n > 0 else None


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
    except Exception as exc:  # noqa: BLE001 - library raises many exception types
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

    # Group the flat ingredient list, then parse each line into structured fields.
    grouped = group_ingredients([str(i) for i in ingredients])
    groups = [
        {
            "title": g["title"],
            "ingredients": [parse_ingredient(line) for line in g["ingredients"]],
        }
        for g in grouped
    ]

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
