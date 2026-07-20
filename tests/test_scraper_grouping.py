"""Tests for ingredient-section reconstruction in the scraper.

These exercise the pure grouping helpers with a fake scraper object and an HTML
fixture, so they run offline (no network / no live site).
"""
from bs4 import BeautifulSoup

from app.services.scraper import (
    _build_groups,
    _has_sections,
    _native_groups,
    _soup_groups,
)


class _FakeGroup:
    def __init__(self, purpose, ingredients):
        self.purpose = purpose
        self.ingredients = ingredients


class _FakeScraper:
    """Minimal stand-in exposing the bits the grouping helpers touch."""

    def __init__(self, html="", native=None, native_raises=False):
        self.soup = BeautifulSoup(html, "html.parser")
        self._native = native
        self._native_raises = native_raises

    def ingredient_groups(self):
        if self._native_raises:
            raise RuntimeError("plugin selectors no longer match")
        if self._native is None:
            return []
        return [_FakeGroup(p, ings) for p, ings in self._native]


# HTML shaped like BBC Good Food: each section is a heading + list as siblings,
# with an unrelated "Nutrition" heading elsewhere on the page.
SECTIONED_HTML = """
<h2>Nutrition</h2>
<section>
  <ul class="ingredients-list">
    <li>2 x 100g salmon fillets</li>
  </ul>
</section>
<section>
  <h3 class="ingredients-list__heading">For the marinade</h3>
  <ul class="ingredients-list">
    <li>2 tsp soy sauce</li>
    <li>1 garlic clove finely chopped</li>
  </ul>
</section>
<section>
  <h3 class="ingredients-list__heading">For the noodles</h3>
  <ul class="ingredients-list">
    <li>85g rice noodle</li>
    <li>2 tsp sesame oil</li>
  </ul>
</section>
"""

SECTIONED_FLAT = [
    "2 x 100g salmon fillets",
    "2 tsp soy sauce",
    "1 garlic clove finely chopped",
    "85g rice noodle",
    "2 tsp sesame oil",
]


def test_has_sections():
    assert _has_sections([{"title": "For the sauce", "lines": ["x"]}]) is True
    assert _has_sections([{"title": None, "lines": ["x"]}]) is False
    assert _has_sections(None) is False
    assert _has_sections([]) is False


def test_native_groups_preferred():
    scraper = _FakeScraper(
        native=[
            ("For the sauce", ["200ml passata", "1 onion"]),
            (None, ["salt"]),
        ]
    )
    groups = _native_groups(scraper)
    assert groups == [
        {"title": "For the sauce", "lines": ["200ml passata", "1 onion"]},
        {"title": None, "lines": ["salt"]},
    ]


def test_native_groups_swallows_plugin_errors():
    scraper = _FakeScraper(native_raises=True)
    assert _native_groups(scraper) is None


def test_soup_groups_reconstructs_sections_and_ignores_unrelated_heading():
    scraper = _FakeScraper(html=SECTIONED_HTML)
    groups = _soup_groups(scraper, SECTIONED_FLAT)
    titles = [g["title"] for g in groups]
    # First list has no sibling heading -> main group (NOT "Nutrition").
    assert titles == [None, "For the marinade", "For the noodles"]
    assert groups[1]["lines"] == ["2 tsp soy sauce", "1 garlic clove finely chopped"]


def test_soup_groups_bails_when_ingredients_not_found():
    scraper = _FakeScraper(html=SECTIONED_HTML)
    assert _soup_groups(scraper, ["something totally different"]) is None


def test_build_groups_uses_soup_when_native_missing():
    scraper = _FakeScraper(html=SECTIONED_HTML, native=None)
    groups = _build_groups(scraper, SECTIONED_FLAT)
    titles = [g["title"] for g in groups]
    assert "For the marinade" in titles and "For the noodles" in titles
    # Ingredients are parsed into structured dicts.
    marinade = next(g for g in groups if g["title"] == "For the marinade")
    assert marinade["ingredients"][0]["unit"] == "tsp"


def test_build_groups_falls_back_to_flat_heuristic():
    # No native groups, no usable soup sections -> single default group.
    scraper = _FakeScraper(html="", native=None)
    flat = ["200g flour", "2 eggs"]
    groups = _build_groups(scraper, flat)
    assert len(groups) == 1 and groups[0]["title"] is None
    assert len(groups[0]["ingredients"]) == 2
